import os
import sys

# Ensure PySpark workers match current Python 3.11 executable environment
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Load environment
from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
sys.path.append(PROJECT_ROOT)

# FastAPI App
app = FastAPI(
    title="Enterprise Retail Lakehouse Platform API",
    description="Backend API for enterprise sales analytics, ML forecasting, inventory risk, and fraud detection.",
    version="1.0.0"
)

# CORS middleware to support local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection manager
_cached_engine = None
_cached_db_type = None

def get_db_connection():
    global _cached_engine, _cached_db_type
    if _cached_engine is not None:
        return _cached_engine, _cached_db_type

    import sqlalchemy as sa
    db_url = os.getenv("DATABASE_URL")
    fallback_db = os.path.join(PROJECT_ROOT, "retail_fallback.db")
    
    # Try PostgreSQL first
    try:
        engine = sa.create_engine(db_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        _cached_engine, _cached_db_type = engine, "postgres"
        return _cached_engine, _cached_db_type
    except Exception:
        # Fallback to SQLite
        if not os.path.exists(fallback_db) or os.path.getsize(fallback_db) == 0:
            print("Fallback SQLite database missing. Automatically generating seed data...")
            try:
                from src.generator.generate_data import SyntheticDataGenerator
                from src.analytics.forecaster import run_sales_forecast
                from src.analytics.fraud_scorer import score_fraud

                gen = SyntheticDataGenerator(fallback_db_path=fallback_db)
                gen.create_schema()
                gen.run_generation(days_back=30)
                run_sales_forecast()
                score_fraud()
            except Exception as se:
                print(f"Failed to auto-heal database: {se}")

        engine = sa.create_engine(f"sqlite:///{fallback_db}")
        _cached_engine, _cached_db_type = engine, "sqlite"
        return _cached_engine, _cached_db_type

class StatusUpdate(BaseModel):
    status: str

# 1. Endpoint: Executive Overview
@app.get("/api/v1/overview")
def get_overview(channel: Optional[str] = None):
    engine, db_type = get_db_connection()
    try:
        tx_df = pd.read_sql("SELECT * FROM silver_transactions", con=engine)
        ret_df = pd.read_sql("SELECT * FROM silver_returns", con=engine)
        cust_df = pd.read_sql("SELECT * FROM silver_customers", con=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database read failure: {e}")

    if tx_df.empty:
        return {"revenue": 0.0, "margin_pct": 0.0, "return_rate_pct": 0.0, "active_customers": 0, "dq_score": 100.0, "alert_count": 0}

    # Filter channel if requested
    if channel:
        tx_df = tx_df[tx_df['channel'] == channel]
        # Align returns
        ret_df = ret_df[ret_df['transaction_id'].isin(tx_df['transaction_id'])]

    tx_df['net_sales'] = tx_df['quantity'].astype(float) * tx_df['unit_price'].astype(float) - tx_df['discount'].astype(float)
    
    # Calculate costs (from products table)
    try:
        prod_df = pd.read_sql("SELECT id as product_id, cost FROM silver_products", con=engine)
        tx_prod = pd.merge(tx_df, prod_df, on='product_id', how='left')
        tx_prod['cost'] = tx_prod['cost'].fillna(0.0).astype(float)
        total_cost = (tx_prod['quantity'].astype(float) * tx_prod['cost']).sum()
    except Exception:
        total_cost = tx_df['net_sales'].sum() * 0.6 # Fallback cost 60% of sales

    total_sales = tx_df['net_sales'].sum()
    gross_margin = ((total_sales - total_cost) / total_sales * 100) if total_sales > 0 else 0.0
    
    total_returns = ret_df['refund_amount'].astype(float).sum()
    return_rate = (total_returns / total_sales * 100) if total_sales > 0 else 0.0
    
    active_custs = tx_df['customer_id'].dropna().nunique()

    # Load Data Quality Score
    dq_score = 98.4 # Fallback
    audit_path = os.path.join(PROJECT_ROOT, "lakehouse", "silver", "dq_audit_log.json")
    if os.path.exists(audit_path):
        try:
            with open(audit_path, 'r') as f:
                dq_logs = json.load(f)
                if dq_logs:
                    dq_score = np.mean([entry["quality_score"] for entry in dq_logs])
        except Exception:
            pass

    return {
        "revenue": round(total_sales, 2),
        "margin_pct": round(gross_margin, 2),
        "return_rate_pct": round(return_rate, 2),
        "active_customers": active_custs,
        "dq_score": round(dq_score, 1),
        "alert_count": int(tx_df['quantity'].lt(0).sum()) # count anomalies
    }

# 2. Endpoint: Sales Trends & Forecast
@app.get("/api/v1/sales/trends")
def get_trends(channel: Optional[str] = None, category: Optional[str] = None):
    engine, db_type = get_db_connection()
    try:
        query = """
            SELECT t.transaction_timestamp, t.channel, p.category, t.quantity, t.unit_price, t.discount
            FROM silver_transactions t
            LEFT JOIN silver_products p ON t.product_id = p.id
        """
        tx_df = pd.read_sql(query, con=engine)
        if tx_df.empty:
            return {"trends": [], "metrics": {"mae": 0.0, "rmse": 0.0, "wape": 0.0}}
            
        tx_df['transaction_timestamp'] = pd.to_datetime(tx_df['transaction_timestamp'], format='mixed', errors='coerce')
        tx_df['date_day'] = tx_df['transaction_timestamp'].dt.date
        tx_df['net_sales'] = pd.to_numeric(tx_df['quantity'], errors='coerce').fillna(1.0) * pd.to_numeric(tx_df['unit_price'], errors='coerce').fillna(0.0) - pd.to_numeric(tx_df['discount'], errors='coerce').fillna(0.0)
        
        if channel and channel != "ALL":
            tx_df = tx_df[tx_df['channel'] == channel]
        if category and category != "ALL":
            tx_df = tx_df[tx_df['category'] == category]
            
        hist_sales = tx_df.groupby('date_day')['net_sales'].sum().reset_index()
        hist_sales.rename(columns={'net_sales': 'actual'}, inplace=True)
        hist_sales['date_day'] = hist_sales['date_day'].astype(str)
        
        target_channel = channel if (channel and channel != "ALL") else "ALL"
        target_category = category if (category and category != "ALL") else "ALL"

        # Load forecast matching channel and category slice
        try:
            fc_df = pd.read_sql(
                "SELECT date_day, forecast_sales as forecast, metrics_json FROM fact_sales_forecast WHERE channel = :ch AND category = :cat", 
                con=engine, 
                params={"ch": target_channel, "cat": target_category}
            )
            if fc_df.empty:
                fc_df = pd.read_sql("SELECT date_day, forecast_sales as forecast, metrics_json FROM fact_sales_forecast WHERE channel = 'ALL' AND category = 'ALL'", con=engine)
            fc_df['date_day'] = pd.to_datetime(fc_df['date_day'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
        except Exception:
            fc_df = pd.DataFrame(columns=['date_day', 'forecast', 'metrics_json'])
            
        # Combine last 14 historical days + forecast days
        hist_recent = hist_sales.sort_values('date_day').tail(14)
        combined = pd.merge(hist_recent, fc_df, on='date_day', how='outer')
        combined = combined.sort_values('date_day').fillna(0)
        
        # Extract metrics from forecast
        metrics = {"mae": 0.0, "rmse": 0.0, "wape": 0.0}
        if not fc_df.empty and 'metrics_json' in fc_df.columns:
            try:
                metrics_val = fc_df.iloc[0]['metrics_json']
                if isinstance(metrics_val, str) and metrics_val:
                    metrics = json.loads(metrics_val)
                elif isinstance(metrics_val, dict):
                    metrics = metrics_val
            except Exception:
                pass

        return {
            "trends": combined.to_dict(orient="records"),
            "metrics": metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trends: {e}")

# 3. Endpoint: Customer RFM Segments
@app.get("/api/v1/customers/segments")
def get_segments():
    engine, db_type = get_db_connection()
    try:
        tx_df = pd.read_sql("SELECT * FROM silver_transactions", con=engine)
        cust_df = pd.read_sql("SELECT * FROM silver_customers", con=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database read failure: {e}")

    if tx_df.empty:
        return {"segments": {}, "retention_rate": 0}

    # Calculate Recency, Frequency, Monetary value
    tx_df['transaction_timestamp'] = pd.to_datetime(tx_df['transaction_timestamp'], format='mixed', errors='coerce')
    max_date = tx_df['transaction_timestamp'].max()
    
    tx_df['net_sales'] = pd.to_numeric(tx_df['quantity'], errors='coerce').fillna(1.0) * pd.to_numeric(tx_df['unit_price'], errors='coerce').fillna(0.0) - pd.to_numeric(tx_df['discount'], errors='coerce').fillna(0.0)
    
    rfm = tx_df.groupby('customer_id').agg(
        recency=('transaction_timestamp', lambda x: (max_date - x.max()).days),
        frequency=('transaction_id', 'nunique'),
        monetary=('net_sales', 'sum')
    ).reset_index()

    # Define segments based on percentiles
    def segment_customer(row):
        if row['recency'] <= 7 and row['frequency'] >= 5 and row['monetary'] >= 1000:
            return "Champions"
        elif row['recency'] <= 14 and row['frequency'] >= 3:
            return "Loyal Customers"
        elif row['recency'] > 20 and row['frequency'] >= 3:
            return "At Risk"
        elif row['recency'] <= 10 and row['frequency'] == 1:
            return "New Customers"
        else:
            return "Hibernating"

    rfm['segment'] = rfm.apply(segment_customer, axis=1)
    seg_counts = rfm['segment'].value_value = rfm['segment'].value_counts().to_dict()

    # Calculate Retention Rate (customers with >1 transactions)
    repeat_customers = rfm[rfm['frequency'] > 1].shape[0]
    total_customers = rfm.shape[0]
    retention_rate = (repeat_customers / total_customers * 100) if total_customers > 0 else 0.0

    return {
        "segments": seg_counts,
        "retention_rate": round(retention_rate, 2),
        "total_scored": total_customers
    }

# 4. Endpoint: Inventory Risk alerts
@app.get("/api/v1/inventory/alerts")
def get_inventory():
    engine, db_type = get_db_connection()
    try:
        prod_df = pd.read_sql("SELECT id as product_id, name, price FROM silver_products", con=engine)
        move_df = pd.read_sql("SELECT * FROM silver_inventory_movements", con=engine)
        store_df = pd.read_sql("SELECT id as store_id, name as store_name FROM silver_stores", con=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database read failure: {e}")

    if move_df.empty:
        return []

    # Calculate stock-on-hand per product & store
    stock = move_df.groupby(['product_id', 'store_id'])['quantity'].sum().reset_index()
    stock.rename(columns={'quantity': 'stock_on_hand'}, inplace=True)
    
    # Calculate average daily sales (last 30 days)
    sales = move_df[move_df['movement_type'] == 'SALE'].copy()
    sales['quantity'] = sales['quantity'].abs()
    
    daily_sales = sales.groupby(['product_id', 'store_id'])['quantity'].sum().reset_index()
    daily_sales['avg_daily_sales'] = daily_sales['quantity'] / 30.0
    daily_sales.drop(columns=['quantity'], inplace=True)
    
    # Combine stock and sales rates
    inv_health = pd.merge(stock, daily_sales, on=['product_id', 'store_id'], how='left')
    inv_health['avg_daily_sales'] = inv_health['avg_daily_sales'].fillna(0.1) # Avoid div by zero
    inv_health['stock_on_hand'] = inv_health['stock_on_hand'].clip(lower=0)
    
    # Compute metrics
    inv_health['days_of_supply'] = inv_health['stock_on_hand'] / inv_health['avg_daily_sales']
    
    # Sell-through rate approximation
    inv_health['sell_through_pct'] = (inv_health['avg_daily_sales'] * 30) / (inv_health['avg_daily_sales'] * 30 + inv_health['stock_on_hand']) * 100
    inv_health['sell_through_pct'] = inv_health['sell_through_pct'].fillna(0.0).round(1)

    # Label risks
    def get_risk(days):
        if days < 5: return "High"
        elif days < 15: return "Medium"
        return "Low"

    inv_health['risk_tier'] = inv_health['days_of_supply'].apply(get_risk)
    
    # Reorder Suggestion
    inv_health['reorder_suggestion'] = (inv_health['avg_daily_sales'] * 30 - inv_health['stock_on_hand']).clip(lower=0).round(0)

    # Join metadata
    inv_health = pd.merge(inv_health, prod_df, on='product_id', how='left')
    inv_health = pd.merge(inv_health, store_df, on='store_id', how='left')

    # Convert to JSON records
    records = inv_health.to_dict(orient="records")
    for r in records:
        r['days_of_supply'] = round(r['days_of_supply'], 1)
        r['avg_daily_sales'] = round(r['avg_daily_sales'], 2)
        r['stock_on_hand'] = int(r['stock_on_hand'])
        r['reorder_suggestion'] = int(r['reorder_suggestion'])
        
    return sorted(records, key=lambda x: x['days_of_supply'])

# 5. Endpoint: Fraud review queue
@app.get("/api/v1/fraud/queue")
def get_fraud_queue(tier: Optional[str] = None):
    engine, db_type = get_db_connection()
    try:
        fraud_df = pd.read_sql("SELECT * FROM fact_fraud_queue", con=engine)
        if tier:
            fraud_df = fraud_df[fraud_df['risk_tier'] == tier]
            
        # Parse factors string to JSON
        records = fraud_df.to_dict(orient="records")
        for r in records:
            try:
                r['risk_factors'] = json.loads(r['risk_factors'])
            except Exception:
                r['risk_factors'] = [r['risk_factors']]
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database read failure: {e}")

@app.post("/api/v1/fraud/{tx_id}/status")
def update_fraud_status(tx_id: str, payload: StatusUpdate):
    engine, db_type = get_db_connection()
    try:
        import sqlalchemy as sa
        status = payload.status
        if status not in ["Approved", "Dismissed", "Pending"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be Approved, Dismissed, or Pending.")

        # Update both DBs if available
        sql = f"UPDATE fact_fraud_queue SET review_status = '{status}' WHERE transaction_id = '{tx_id}'"
        
        with engine.begin() as conn:
            conn.execute(sa.text(sql))
            
        # If we are using postgres, sync to fallback SQLite as well
        if db_type == "postgres":
            try:
                fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
                sqlite_engine = sa.create_engine(f"sqlite:///{fallback_db}")
                with sqlite_engine.begin() as sq_conn:
                    sq_conn.execute(sa.text(sql))
            except Exception:
                pass
                
        return {"status": "success", "message": f"Transaction {tx_id} status updated to {status}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update status: {e}")

# 6. Endpoint: Pipeline Health
@app.get("/api/v1/pipeline/health")
def get_pipeline_health():
    # Read the audit file to show table statuses
    audit_path = os.path.join(PROJECT_ROOT, "lakehouse", "silver", "dq_audit_log.json")
    health_data = []
    
    if os.path.exists(audit_path):
        try:
            with open(audit_path, 'r') as f:
                health_data = json.load(f)
        except Exception:
            pass
            
    if not health_data:
        # Default mock entries if file not populated yet
        health_data = [
            {"table_name": "transactions", "bronze_count": 1205, "silver_count": 1180, "quarantine_count": 25, "duplicate_count": 12, "reconciled": True, "quality_score": 97.9},
            {"table_name": "customers", "bronze_count": 20, "silver_count": 19, "quarantine_count": 1, "duplicate_count": 0, "reconciled": True, "quality_score": 95.0},
            {"table_name": "products", "bronze_count": 21, "silver_count": 21, "quarantine_count": 0, "duplicate_count": 0, "reconciled": True, "quality_score": 100.0}
        ]
        
    return {
        "status": "Healthy",
        "last_execution": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "run_duration_sec": 42.5,
        "tables": health_data
    }

from fastapi import File, UploadFile, Form
from fastapi.responses import PlainTextResponse

# 7. Endpoint: File Upload & Ingestion Pipeline Execution
def adapt_dataframe_to_table_schema(df: pd.DataFrame, table_name: str, engine) -> pd.DataFrame:
    df = df.copy()
    raw_cols = {col: str(col).strip().lower() for col in df.columns}
    df.rename(columns=raw_cols, inplace=True)
    
    # Universal Kaggle Synonym Mapping
    column_synonyms = {
        "order id": "transaction_id",
        "order_id": "transaction_id",
        "invoiceno": "transaction_id",
        "invoice_no": "transaction_id",
        "invoice": "transaction_id",
        
        "order date": "transaction_timestamp",
        "order_date": "transaction_timestamp",
        "invoicedate": "transaction_timestamp",
        "date": "transaction_timestamp",
        "timestamp": "transaction_timestamp",
        
        "customer id": "customer_id",
        "customer_id": "customer_id",
        "customerno": "customer_id",
        
        "product id": "product_id",
        "product_id": "product_id",
        "item_id": "product_id",
        "stockcode": "product_id",
        
        "store id": "store_id",
        "store_id": "store_id",
        "store": "store_id",
        
        "sales": "unit_price",
        "price": "unit_price",
        "amount": "unit_price",
        "total_amount": "unit_price",
        
        "quantity": "quantity",
        "qty": "quantity",
        "quantity_ordered": "quantity",
        
        "discount": "discount",
        "discount_rate": "discount",
        
        "ship mode": "channel",
        "channel": "channel",
        "sales_channel": "channel",
        
        "product name": "name",
        "product_name": "name",
        "item_name": "name",
        "description": "name",
        
        "sub-category": "category",
        "sub_category": "category",
        "category": "category",
        
        "cost": "cost",
        
        "customer name": "first_name",
        "customer_name": "first_name",
        "full_name": "first_name",
        
        "email": "email",
        "phone": "phone",
        "gender": "gender",
        "state": "state",
    }
    
    # Apply column renaming
    rename_map = {}
    for col in df.columns:
        if col in column_synonyms and column_synonyms[col] not in df.columns:
            rename_map[col] = column_synonyms[col]
    df.rename(columns=rename_map, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()]
    
    # Defaults for transaction schema
    if table_name == "transactions":
        if "quantity" not in df.columns:
            df["quantity"] = 1
        if "unit_price" not in df.columns:
            df["unit_price"] = 100.0
        if "discount" not in df.columns:
            df["discount"] = 0.0
        if "channel" not in df.columns:
            df["channel"] = "WEBSITE"
        if "transaction_timestamp" not in df.columns:
            from datetime import datetime
            df["transaction_timestamp"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        else:
            from datetime import datetime
            dt_parsed = pd.to_datetime(df["transaction_timestamp"], format="mixed", errors="coerce")
            df["transaction_timestamp"] = dt_parsed.dt.strftime("%Y-%m-%d %H:%M:%S").fillna(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))

    # Ensure essential unique 'id' primary key column exists
    import uuid
    if "id" not in df.columns or df["id"].duplicated().any():
        df["id"] = [str(uuid.uuid4()) for _ in range(len(df))]

    # Filter to keep ONLY columns present in database table
    import sqlalchemy as sa
    try:
        inspector = sa.inspect(engine)
        table_cols = [c["name"] for c in inspector.get_columns(table_name)]
        valid_cols = [col for col in df.columns if col in table_cols]
        if "id" in table_cols and "id" not in valid_cols:
            valid_cols.append("id")
        return df[valid_cols]
    except Exception:
        return df

# 7. Endpoint: File Upload & Ingestion Pipeline Execution
@app.post("/api/v1/upload/file")
async def upload_dataset_file(table_name: str = Form(...), file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    filename = file.filename.lower()
    content = await file.read()
    
    import io
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), encoding_errors="replace")
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        elif filename.endswith(".json"):
            df = pd.read_json(io.BytesIO(content))
        else:
            try:
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            except Exception:
                df = pd.read_csv(io.BytesIO(content), encoding_errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel/CSV file content: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no rows.")

    engine, db_type = get_db_connection()
    fallback_db = os.path.join(PROJECT_ROOT, "retail_fallback.db")
    import sqlalchemy as sa
    sqlite_engine = sa.create_engine(f"sqlite:///{fallback_db}")

    # Ensure schema exists and adapt DataFrame to exact database table schema
    from src.generator.generate_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator(fallback_db_path=fallback_db)
    gen.create_schema()

    df = adapt_dataframe_to_table_schema(df, table_name, sqlite_engine if db_type == "sqlite" else engine)

    # Insert uploaded data into source table with chunked deduplication
    try:
        existing_ids = df['id'].dropna().astype(str).unique().tolist() if 'id' in df.columns else []
        chunk_size = 500
        if db_type == "postgres":
            if existing_ids:
                with engine.begin() as conn:
                    for i in range(0, len(existing_ids), chunk_size):
                        chunk = existing_ids[i:i+chunk_size]
                        id_str = ", ".join([f"'{str(x)}'" for x in chunk])
                        conn.execute(sa.text(f"DELETE FROM {table_name} WHERE id IN ({id_str})"))
            df.to_sql(table_name, con=engine, if_exists="append", index=False)
        else:
            if existing_ids:
                with sqlite_engine.begin() as conn:
                    for i in range(0, len(existing_ids), chunk_size):
                        chunk = existing_ids[i:i+chunk_size]
                        id_str = ", ".join([f"'{str(x)}'" for x in chunk])
                        conn.execute(sa.text(f"DELETE FROM {table_name} WHERE id IN ({id_str})"))
                    
            df.to_sql(table_name, con=sqlite_engine, if_exists="append", index=False)
            gen.sync_to_silver_sqlite()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to insert uploaded data into table '{table_name}': {e}")

    # Automatically execute ML forecast & fraud scorer
    try:
        from src.analytics.forecaster import run_sales_forecast
        from src.analytics.fraud_scorer import score_fraud
        run_sales_forecast()
        score_fraud()
    except Exception as pe:
        print(f"Analytics refresh note: {pe}")

    return {
        "status": "success",
        "message": f"Successfully ingested {len(df)} rows from '{file.filename}' into '{table_name}' and updated analytics.",
        "table_name": table_name,
        "rows_processed": len(df)
    }

def run_pyspark_async():
    try:
        from src.ingestion.bronze_ingest import run_bronze_pipeline
        from src.ingestion.silver_clean import run_silver_pipeline
        from src.warehouse.sync_to_pg import run_sync_pipeline
        run_bronze_pipeline()
        run_silver_pipeline()
        run_sync_pipeline()
    except Exception as spark_err:
        print(f"PySpark pipeline async notice: {spark_err}")

# 8. Endpoint: Trigger Sample Dataset Generation
@app.post("/api/v1/ingest/sample")
def generate_sample_dataset(background_tasks: BackgroundTasks, days: int = Query(default=30)):
    try:
        from src.generator.generate_data import SyntheticDataGenerator
        from src.analytics.forecaster import run_sales_forecast
        from src.analytics.fraud_scorer import score_fraud

        fallback_db = os.path.join(PROJECT_ROOT, "retail_fallback.db")
        gen = SyntheticDataGenerator(fallback_db_path=fallback_db)
        gen.create_schema()
        gen.run_generation(days_back=days)

        # Run ML Analytics
        run_sales_forecast()
        score_fraud()

        # Schedule heavy PySpark lakehouse sync asynchronously
        background_tasks.add_task(run_pyspark_async)

        return {"status": "success", "message": f"Successfully generated and ingested synthetic Faker dataset for {days} days."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate dataset: {e}")

# 9. Endpoint: Get Template CSV
@app.get("/api/v1/template/{table_name}")
def get_table_csv_template(table_name: str):
    templates = {
        "transactions": "id,transaction_id,customer_id,store_id,channel,product_id,quantity,unit_price,discount,transaction_timestamp\nTXN-UPL-001,TXN-100999,CUST-1001,ST-01,POS,PRD-100,2,1200.00,0.00,2026-07-22 10:00:00\nTXN-UPL-002,TXN-101000,CUST-1002,,WEBSITE,PRD-104,1,89.00,5.00,2026-07-22 11:30:00",
        "customers": "id,first_name,last_name,email,phone,gender,state,birth_date\nCUST-9001,Alex,Morgan,alex.morgan@example.com,+1-555-0199,F,NY,1992-04-12\nCUST-9002,Jordan,Lee,jordan.lee@example.com,+1-555-0198,M,CA,1988-11-23",
        "products": "id,sku,name,category,price,cost\nPRD-900,SKU-ELE-900,Wireless Mechanical Keyboard,Electronics,149.00,70.00\nPRD-901,SKU-APP-901,Waterproof Parka Jacket,Apparel,180.00,85.00",
        "inventory_movements": "id,product_id,store_id,movement_type,quantity,movement_timestamp\nMOV-001,PRD-100,ST-01,RESTOCK,50,2026-07-22 08:00:00\nMOV-002,PRD-104,ST-02,RESTOCK,30,2026-07-22 08:00:00",
        "returns": "id,transaction_id,product_id,quantity,refund_amount,return_reason,return_timestamp\nRET-001,TXN-100999,PRD-100,1,1200.00,DEFECTIVE,2026-07-22 14:00:00",
        "support_tickets": "id,customer_id,issue_category,status,priority,ticket_timestamp\nTKT-9901,CUST-1001,DELIVERY,OPEN,HIGH,2026-07-22 12:00:00"
    }

    if table_name not in templates:
        raise HTTPException(status_code=404, detail=f"No template available for table '{table_name}'")

    return PlainTextResponse(content=templates[table_name], media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={table_name}_template.csv"})

# 10. Endpoint: Clear Dataset
@app.post("/api/v1/data/clear")
def clear_all_dataset():
    try:
        from src.generator.cleanup_data import cleanup
        cleanup()
        return {"status": "success", "message": "All database records and Lakehouse files have been cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear data: {e}")

# 11. Health Check
@app.get("/health")
def health():
    return {"status": "healthy", "service": "retail-lakehouse-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
