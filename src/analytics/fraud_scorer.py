import os
import sys
import json
from datetime import datetime, timedelta
import pandas as pd

# Load dotenv
from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"

def get_db_connection():
    import sqlalchemy as sa
    db_url = os.getenv("DATABASE_URL")
    fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
    try:
        engine = sa.create_engine(db_url, connect_args={"connect_timeout": 3})
        # Test connection
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return engine, "postgres"
    except Exception:
        engine = sa.create_engine(f"sqlite:///{fallback_db}")
        return engine, "sqlite"

def score_fraud():
    print("\n--- Running Explainable Fraud Risk Scorer ---")
    engine, db_type = get_db_connection()
    print(f"Connected to {db_type} database.")

    # 1. Fetch transactions, returns, and customers
    try:
        tx_df = pd.read_sql("SELECT * FROM silver_transactions", con=engine)
        cust_df = pd.read_sql("SELECT * FROM silver_customers", con=engine)
        ret_df = pd.read_sql("SELECT * FROM silver_returns", con=engine)
    except Exception as e:
        print(f"Failed to fetch silver tables: {e}. Cannot score fraud.")
        return

    if tx_df.empty:
        print("No transactions found to score.")
        return

    print(f"Scoring {len(tx_df)} transactions...")

    # Build customer aggregations for context
    # High return rates, duplicate behaviors, velocity check
    tx_df['transaction_timestamp'] = pd.to_datetime(tx_df['transaction_timestamp'])
    
    # Calculate returns per customer
    ret_counts = ret_df.groupby('transaction_id')['quantity'].sum().reset_index()
    ret_counts.rename(columns={'quantity': 'returned_qty'}, inplace=True)
    
    # Merge return indicators
    tx_ret = pd.merge(tx_df, ret_counts, on='transaction_id', how='left')
    tx_ret['returned_qty'] = tx_ret['returned_qty'].fillna(0)

    # Sort transactions chronologically for velocity analysis
    tx_ret = tx_ret.sort_values(by=['customer_id', 'transaction_timestamp']).reset_index(drop=True)
    
    # Calculate transaction velocity (rolling transaction count within 1 hour)
    tx_ret['time_diff_prev'] = tx_ret.groupby('customer_id')['transaction_timestamp'].diff()
    
    # Calculate customer total spend and counts
    cust_spend = tx_df.groupby('customer_id')['quantity'].count().to_dict()

    fraud_records = []
    score_version = "1.0.0"

    for idx, row in tx_ret.iterrows():
        score = 0
        factors = []
        cust_id = row['customer_id']
        price = float(row['unit_price'] or 0)
        qty = int(row['quantity'] or 0)
        total_val = price * qty - float(row['discount'] or 0)
        
        # Risk factor 1: Transaction value threshold
        if total_val > 1500:
            score += 35
            factors.append(f"High order value of ${total_val:.2f} (exceeds threshold of $1500)")
        elif total_val > 800:
            score += 15
            factors.append(f"Medium-high order value of ${total_val:.2f}")

        # Risk factor 2: Velocity Check (frequency of purchases)
        # Check if customer has multiple transactions very close in time
        cust_txs = tx_ret[tx_ret['customer_id'] == cust_id]
        if len(cust_txs) > 1:
            recent_txs = cust_txs[
                (cust_txs['transaction_timestamp'] <= row['transaction_timestamp']) & 
                (cust_txs['transaction_timestamp'] >= row['transaction_timestamp'] - timedelta(hours=1))
            ]
            recent_count = len(recent_txs)
            if recent_count >= 5:
                score += 40
                factors.append(f"High transaction velocity: {recent_count} transactions in the last hour")
            elif recent_count >= 3:
                score += 20
                factors.append(f"Elevated transaction velocity: {recent_count} transactions in the last hour")

        # Risk factor 3: Malformed customer details
        cust_profile = cust_df[cust_df['id'] == cust_id]
        if not cust_profile.empty:
            cust_row = cust_profile.iloc[0]
            email = cust_row.get('email', '')
            gender = cust_row.get('gender', '')
            
            if '@example.com' not in email and 'malformed' in email:
                score += 15
                factors.append("Customer profile has invalid/malformed email syntax")
            if gender not in ['M', 'F', 'OTHER', 'UNKNOWN']:
                score += 10
                factors.append(f"Customer profile has unrecognized gender code '{gender}'")

        # Risk factor 4: Return rate
        if cust_id:
            cust_returns = ret_df[ret_df['transaction_id'].isin(cust_txs['transaction_id'])]
            if len(cust_txs) >= 3 and len(cust_returns) / len(cust_txs) > 0.4:
                score += 20
                factors.append(f"Customer has a high return frequency ratio ({len(cust_returns)/len(cust_txs)*100:.0f}%)")

        # Cap score at 100
        score = min(score, 100)
        
        # Risk Tiers
        if score >= 70:
            risk_tier = "High"
            review_status = "Pending"
        elif score >= 35:
            risk_tier = "Medium"
            review_status = "Pending"
        else:
            risk_tier = "Low"
            review_status = "Approved"

        # If score is 0, add default factor
        if not factors:
            factors.append("Normal purchase indicators")

        fraud_records.append({
            "transaction_line_id": row['id'],
            "transaction_id": row['transaction_id'],
            "customer_id": cust_id,
            "transaction_timestamp": row['transaction_timestamp'],
            "net_sales": total_val,
            "fraud_score": score,
            "risk_tier": risk_tier,
            "risk_factors": json.dumps(factors),
            "score_version": score_version,
            "review_status": review_status,
            "created_at": datetime.utcnow()
        })

    fraud_df = pd.DataFrame(fraud_records)
    
    # Save to PostgreSQL
    try:
        print("Saving fraud risk scoring results to PostgreSQL...")
        fraud_df['created_at'] = fraud_df['created_at'].dt.tz_localize(None)
        fraud_df['transaction_timestamp'] = pd.to_datetime(fraud_df['transaction_timestamp']).dt.tz_localize(None)
        fraud_df.to_sql("fact_fraud_queue", con=engine, if_exists="replace", index=False)
        print("Successfully saved fraud data to PostgreSQL.")
    except Exception as e:
        print(f"Could not save fraud data to PostgreSQL: {e}")

    # Save to SQLite
    try:
        fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
        import sqlalchemy as sa
        sqlite_engine = sa.create_engine(f"sqlite:///{fallback_db}")
        print(f"Saving fraud risk scoring results to SQLite: {fallback_db}")
        fraud_df.to_sql("fact_fraud_queue", con=sqlite_engine, if_exists="replace", index=False)
        print("Successfully saved fraud data to SQLite.")
    except Exception as e:
        print(f"Could not save fraud data to SQLite: {e}")

if __name__ == "__main__":
    score_fraud()
