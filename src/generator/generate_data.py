import os
import sys
import uuid
import random
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import sqlite3
from faker import Faker

fake = Faker()

# Import SQLAlchemy for PostgreSQL interactions
try:
    import sqlalchemy as sa
    from sqlalchemy.orm import declarative_base, sessionmaker
    HAS_SA = True
except ImportError:
    HAS_SA = False

# Setup directories
PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)

# Generate baseline entities
STATES = ["NY", "CA", "TX", "FL", "IL", "PA", "OH", "MI", "NC", "GA", "WA", "MA"]
CATEGORIES = ["Electronics", "Apparel", "Home & Living", "Beauty", "Sports & Outdoors", "Grocery"]
CHANNELS = ["POS", "WEBSITE", "MOBILE_APP"]
SUPPORT_CATEGORIES = ["DELIVERY", "PAYMENT", "DEFECTIVE", "REFUND", "OTHER"]
SUPPORT_STATUSES = ["OPEN", "IN_PROGRESS", "RESOLVED"]
SUPPORT_PRIORITIES = ["LOW", "MEDIUM", "HIGH"]
REACTION_CHANNELS = ["EMAIL", "SMS", "SOCIAL", "SEARCH"]

class SyntheticDataGenerator:
    def __init__(self, db_url=None, fallback_db_path=None):
        self.db_url = db_url or os.getenv("SOURCE_DATABASE_URL", "postgresql://retail_user:retail_pass@localhost:5432/retail_source")
        self.fallback_db_path = fallback_db_path or os.getenv("FALLBACK_DB_PATH", os.path.join(PROJECT_ROOT, "retail_fallback.db"))
        self.use_postgres = False
        self.conn = None
        self.engine = None
        
        # Detect mode
        if HAS_SA:
            try:
                self.engine = sa.create_engine(self.db_url, connect_args={"connect_timeout": 3})
                # Check connection
                with self.engine.connect() as check_conn:
                    check_conn.execute(sa.text("SELECT 1"))
                self.use_postgres = True
                print(f"Connected to PostgreSQL source database at {self.db_url}")
            except Exception as e:
                print(f"Failed to connect to PostgreSQL ({e}). Falling back to local SQLite at {self.fallback_db_path}")
        else:
            print(f"SQLAlchemy or Psycopg2 not available. Falling back to local SQLite at {self.fallback_db_path}")

        if not self.use_postgres:
            self.conn = sqlite3.connect(self.fallback_db_path)
            print(f"Initialized SQLite database at {self.fallback_db_path}")

    def execute_ddl(self, sql_list):
        if self.use_postgres:
            with self.engine.begin() as conn:
                for sql in sql_list:
                    # Clean up SERIAL / AUTOINCREMENT between engines
                    sql_pg = sql.replace("AUTOINCREMENT", "").replace("DATETIME", "TIMESTAMP").replace("TEXT", "VARCHAR(255)")
                    conn.execute(sa.text(sql_pg))
        else:
            cursor = self.conn.cursor()
            for sql in sql_list:
                cursor.execute(sql)
            self.conn.commit()

    def execute_insert(self, table, data_list):
        if not data_list:
            return
        
        columns = list(data_list[0].keys())
        
        if self.use_postgres:
            # PostgreSQL Insert
            meta = sa.MetaData()
            meta.reflect(bind=self.engine)
            
            # Create table reference on-the-fly
            sa_table = sa.Table(table, meta, autoload_with=self.engine)
            with self.engine.begin() as conn:
                conn.execute(sa_table.insert(), data_list)
        else:
            # SQLite Insert
            col_placeholders = ", ".join([f":{c}" for c in columns])
            sql = f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({col_placeholders})"
            cursor = self.conn.cursor()
            cursor.executemany(sql, data_list)
            self.conn.commit()

    def create_schema(self):
        print("Creating schemas and source tables...")
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS customers (
                id VARCHAR(100) PRIMARY KEY,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                email VARCHAR(100),
                phone VARCHAR(50),
                gender VARCHAR(20),
                state VARCHAR(20),
                birth_date VARCHAR(50),
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(100) PRIMARY KEY,
                sku VARCHAR(50) UNIQUE,
                name VARCHAR(150),
                category VARCHAR(100),
                price DECIMAL(10, 2),
                cost DECIMAL(10, 2),
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS stores (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(150),
                city VARCHAR(100),
                state VARCHAR(20),
                country VARCHAR(100),
                square_footage INTEGER,
                open_date VARCHAR(50)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id VARCHAR(100) PRIMARY KEY,
                transaction_id VARCHAR(100),
                customer_id VARCHAR(100),
                store_id VARCHAR(100),
                channel VARCHAR(50),
                product_id VARCHAR(100),
                quantity INTEGER,
                unit_price DECIMAL(10, 2),
                discount DECIMAL(10, 2),
                transaction_timestamp TIMESTAMP,
                created_at TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS returns (
                id VARCHAR(100) PRIMARY KEY,
                transaction_id VARCHAR(100),
                product_id VARCHAR(100),
                quantity INTEGER,
                refund_amount DECIMAL(10, 2),
                return_reason VARCHAR(255),
                return_timestamp TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS inventory_movements (
                id VARCHAR(100) PRIMARY KEY,
                product_id VARCHAR(100),
                store_id VARCHAR(100),
                movement_type VARCHAR(50),
                quantity INTEGER,
                movement_timestamp TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS marketing_campaigns (
                id VARCHAR(100) PRIMARY KEY,
                campaign_name VARCHAR(150),
                channel VARCHAR(50),
                cost DECIMAL(10, 2),
                impressions INTEGER,
                clicks INTEGER,
                conversions INTEGER,
                campaign_date VARCHAR(50)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id VARCHAR(100) PRIMARY KEY,
                customer_id VARCHAR(100),
                issue_category VARCHAR(100),
                status VARCHAR(50),
                priority VARCHAR(50),
                ticket_timestamp TIMESTAMP,
                resolution_timestamp TIMESTAMP
            );
            """
        ]
        self.execute_ddl(ddl)
        print("Tables initialized successfully.")

    def run_generation(self, days_back=30):
        print(f"Generating synthetic retail data for last {days_back} days...")
        now = datetime.utcnow()
        start_date = now - timedelta(days=days_back)
        
        # 1. Generate Stores
        stores = [
            {"id": "ST-01", "name": "Flagship Manhattan", "city": "New York", "state": "NY", "country": "USA", "square_footage": 25000, "open_date": "2018-05-15"},
            {"id": "ST-02", "name": "Silicon Valley Hub", "city": "San Jose", "state": "CA", "country": "USA", "square_footage": 18000, "open_date": "2020-11-01"},
            {"id": "ST-03", "name": "Texas Retail Giant", "city": "Austin", "state": "TX", "country": "USA", "square_footage": 32000, "open_date": "2015-09-10"},
            {"id": "ST-04", "name": "Miami Sunshine Spot", "city": "Miami", "state": "FL", "country": "USA", "square_footage": 12000, "open_date": "2021-03-22"},
            {"id": "ST-05", "name": "Chicago Wind Store", "city": "Chicago", "state": "IL", "country": "USA", "square_footage": 22000, "open_date": "2019-07-04"}
        ]
        self.execute_insert("stores", stores)
        print(f"Generated {len(stores)} stores.")

        # 2. Generate Products
        categories_products = {
            "Electronics": [("OLED Smart TV", 1200.00, 800.00), ("Noise Cancelling Headphones", 350.00, 200.00), ("Smartwatch Series 9", 399.00, 250.00), ("Laptop Pro 15", 1800.00, 1200.00)],
            "Apparel": [("Denim Jacket", 89.00, 35.00), ("Running Shoes Zoom", 120.00, 50.00), ("Cotton Crewneck Tee", 25.00, 8.00), ("Athletic Leggings", 60.00, 22.00)],
            "Home & Kitchen": [("Air Fryer Max", 150.00, 75.00), ("Espresso Coffee Maker", 599.00, 350.00), ("Blender 1000W", 99.00, 45.00), ("Robot Vacuum", 299.00, 150.00)],
            "Beauty": [("Anti-Aging Serum", 85.00, 30.00), ("Hydrating Moisturizer", 45.00, 15.00), ("Matte Lipstick Red", 28.00, 10.00)],
            "Sports & Outdoors": [("Camping Tent 4-Person", 199.00, 95.00), ("Yoga Mat Premium", 50.00, 18.00), ("Adjustable Dumbbell Set", 349.00, 180.00)],
            "Grocery": [("Organic Coffee Beans", 18.00, 8.00), ("Premium Olive Oil", 24.00, 12.00), ("Energy Bar 12-Pack", 20.00, 9.00)]
        }

        products = []
        prod_index = 100
        for cat, items in categories_products.items():
            for name, price, cost in items:
                products.append({
                    "id": f"PRD-{prod_index}",
                    "sku": f"SKU-{cat[:3].upper()}-{prod_index}",
                    "name": name,
                    "category": cat,
                    "price": price,
                    "cost": cost,
                    "created_at": start_date,
                    "updated_at": start_date
                })
                prod_index += 1
        self.execute_insert("products", products)
        print(f"Generated {len(products)} products.")

        # 3. Generate Customers with Faker
        customers = []
        for i in range(30):
            first = fake.first_name()
            last = fake.last_name()
            gender = random.choice(["M", "F"])
            created = start_date + timedelta(days=random.randint(0, 10))
            email = fake.ascii_company_email() if random.random() > 0.05 else f"{first.lower()}{last.lower()}"
            customers.append({
                "id": f"CUST-{1000 + i}",
                "first_name": first,
                "last_name": last,
                "email": email,
                "phone": fake.phone_number(),
                "gender": gender,
                "state": fake.state_abbr(),
                "birth_date": fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%Y-%m-%d"),
                "created_at": created,
                "updated_at": created
            })
        self.execute_insert("customers", customers)
        print(f"Generated {len(customers)} customers using Faker.")

        # 4. Generate Transactions & Returns & Support & Campaigns
        transactions = []
        returns = []
        inventory_movements = []
        marketing_campaigns = []
        support_tickets = []
        
        # Setup initial inventory level
        for p in products:
            for s in stores:
                inventory_movements.append({
                    "id": str(uuid.uuid4()),
                    "product_id": p["id"],
                    "store_id": s["id"],
                    "movement_type": "RESTOCK",
                    "quantity": random.randint(100, 200),
                    "movement_timestamp": start_date
                })

        # Iterate day-by-day to simulate continuous ingestion and CDC behavior
        current_day = start_date
        tx_index = 100000
        
        while current_day < now:
            # 4.1 Marketing campaign daily data
            if random.random() < 0.3:
                camp_name = f"Campaign {current_day.strftime('%Y-%b')}"
                marketing_campaigns.append({
                    "id": str(uuid.uuid4()),
                    "campaign_name": camp_name,
                    "channel": random.choice(REACTION_CHANNELS),
                    "cost": float(random.randint(500, 3000)),
                    "impressions": random.randint(10000, 50000),
                    "clicks": random.randint(500, 3000),
                    "conversions": random.randint(10, 100),
                    "campaign_date": current_day.strftime("%Y-%m-%d")
                })
            
            # 4.2 Customer detail updates (SCD Type 2 simulator)
            # Pick a customer and update their email or state
            if random.random() < 0.1:
                cust_to_update = random.choice(customers)
                cust_to_update["state"] = random.choice(STATES)
                cust_to_update["updated_at"] = current_day
                # Run an update statement
                if self.use_postgres:
                    with self.engine.begin() as conn:
                        conn.execute(sa.text(f"UPDATE customers SET state = '{cust_to_update['state']}', updated_at = '{current_day}' WHERE id = '{cust_to_update['id']}'"))
                else:
                    cursor = self.conn.cursor()
                    cursor.execute(f"UPDATE customers SET state = '{cust_to_update['state']}', updated_at = ? WHERE id = ?", (current_day, cust_to_update['id']))
                    self.conn.commit()

            # 4.3 Daily transactions
            daily_tx_count = random.randint(20, 50)
            for _ in range(daily_tx_count):
                tx_index += 1
                cust = random.choice(customers)
                prod = random.choice(products)
                store = random.choice(stores)
                channel = random.choice(CHANNELS)
                qty = random.randint(1, 4)
                
                # Check discount
                disc = 0.0
                if random.random() < 0.2:
                    disc = round(random.uniform(2.0, 15.0), 2)
                
                # Dynamic timestamp within the day
                tx_time = current_day + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
                
                # Intentional anomaly injection
                is_duplicate = random.random() < 0.05
                is_malformed = random.random() < 0.02
                is_late_arriving = random.random() < 0.04
                
                if is_late_arriving:
                    # Backdate by 3 to 7 days
                    tx_time = tx_time - timedelta(days=random.randint(3, 7))

                if is_malformed:
                    # Negative quantity or price set to Null
                    price_val = None if random.random() > 0.5 else -10.0
                    qty = -2 if price_val is not None else 1
                else:
                    price_val = prod["price"]

                tx_data = {
                    "id": str(uuid.uuid4()),
                    "transaction_id": f"TXN-{tx_index}",
                    "customer_id": cust["id"] if random.random() > 0.05 else None, # Some nulls
                    "store_id": store["id"] if channel == "POS" else None, # Online stores have no store_id
                    "channel": channel,
                    "product_id": prod["id"],
                    "quantity": qty,
                    "unit_price": price_val,
                    "discount": disc,
                    "transaction_timestamp": tx_time,
                    "created_at": tx_time
                }
                
                transactions.append(tx_data)
                
                # Deduplication testing: add the same transaction again with same ID
                if is_duplicate:
                    dup_data = tx_data.copy()
                    dup_data["id"] = str(uuid.uuid4()) # Different envelope ID but identical contents
                    # Insert it shortly after
                    transactions.append(dup_data)
                
                # Inventory movement
                inventory_movements.append({
                    "id": str(uuid.uuid4()),
                    "product_id": prod["id"],
                    "store_id": store["id"] if channel == "POS" else "ST-01", # Assume online orders fulfilled from ST-01
                    "movement_type": "SALE",
                    "quantity": -qty,
                    "movement_timestamp": tx_time
                })

                # 4.4 Returns (2% of transactions get returned)
                if random.random() < 0.02 and not is_malformed:
                    returns.append({
                        "id": str(uuid.uuid4()),
                        "transaction_id": tx_data["transaction_id"],
                        "product_id": tx_data["product_id"],
                        "quantity": tx_data["quantity"],
                        "refund_amount": float(tx_data["quantity"]) * float(tx_data["unit_price"]) - tx_data["discount"],
                        "return_reason": random.choice(["DEFECTIVE", "SIZE_FIT", "MISTAKE", "DISLIKED"]),
                        "return_timestamp": tx_time + timedelta(days=random.randint(1, 5))
                    })
                    
                    # Log return inventory restock
                    inventory_movements.append({
                        "id": str(uuid.uuid4()),
                        "product_id": prod["id"],
                        "store_id": tx_data["store_id"] or "ST-01",
                        "movement_type": "RETURN",
                        "quantity": tx_data["quantity"],
                        "movement_timestamp": tx_time + timedelta(days=random.randint(1, 5))
                    })

                # 4.5 Support tickets
                if random.random() < 0.03:
                    ticket_time = tx_time + timedelta(hours=random.randint(2, 48))
                    resolved_time = ticket_time + timedelta(days=random.randint(1, 3)) if random.random() > 0.3 else None
                    support_tickets.append({
                        "id": f"TKT-{random.randint(10000, 99999)}",
                        "customer_id": cust["id"],
                        "issue_category": random.choice(SUPPORT_CATEGORIES),
                        "status": random.choice(SUPPORT_STATUSES) if resolved_time is None else "RESOLVED",
                        "priority": random.choice(SUPPORT_PRIORITIES),
                        "ticket_timestamp": ticket_time,
                        "resolution_timestamp": resolved_time
                    })

            # Move to next day
            current_day += timedelta(days=1)

        # 4.6 Injection of high-frequency fraud patterns (to test fraud detection engine)
        # Create a single customer that buys many products within minutes
        fraud_customer = customers[0]
        fraud_time = now - timedelta(days=1)
        for i in range(12):
            transactions.append({
                "id": str(uuid.uuid4()),
                "transaction_id": f"TXN-FRAUD-{i}",
                "customer_id": fraud_customer["id"],
                "store_id": "ST-01",
                "channel": "WEBSITE",
                "product_id": products[i % len(products)]["id"],
                "quantity": 5,
                "unit_price": products[i % len(products)]["price"],
                "discount": 0.0,
                "transaction_timestamp": fraud_time + timedelta(minutes=i * 2),
                "created_at": fraud_time + timedelta(minutes=i * 2)
            })

        # Insert everything
        print("Inserting records into database...")
        self.execute_insert("transactions", transactions)
        self.execute_insert("returns", returns)
        self.execute_insert("inventory_movements", inventory_movements)
        self.execute_insert("marketing_campaigns", marketing_campaigns)
        self.execute_insert("support_tickets", support_tickets)

        # Direct sync to silver tables for SQLite fallback
        self.sync_to_silver_sqlite()
        
        print("Data generation complete!")
        print(f"Total Transactions: {len(transactions)}")
        print(f"Total Returns: {len(returns)}")
        print(f"Total Inventory Movements: {len(inventory_movements)}")
        print(f"Total Support Tickets: {len(support_tickets)}")

    def sync_to_silver_sqlite(self):
        if self.use_postgres or not self.conn:
            return
        
        cursor = self.conn.cursor()
        print("Syncing data to Silver tables in SQLite...")
        
        # silver_transactions
        cursor.execute("DROP TABLE IF EXISTS silver_transactions")
        cursor.execute("""
            CREATE TABLE silver_transactions AS
            SELECT id, transaction_id, customer_id, store_id, channel, product_id, quantity, unit_price, discount, transaction_timestamp
            FROM transactions
            WHERE quantity > 0 AND unit_price IS NOT NULL AND unit_price > 0
        """)

        # silver_products
        cursor.execute("DROP TABLE IF EXISTS silver_products")
        cursor.execute("""
            CREATE TABLE silver_products AS
            SELECT id, sku, name, category, price, cost
            FROM products
        """)

        # silver_customers
        cursor.execute("DROP TABLE IF EXISTS silver_customers")
        cursor.execute("""
            CREATE TABLE silver_customers AS
            SELECT id, first_name, last_name, email, phone, gender, state, birth_date
            FROM customers
            WHERE email LIKE '%@%'
        """)

        # silver_stores
        cursor.execute("DROP TABLE IF EXISTS silver_stores")
        cursor.execute("""
            CREATE TABLE silver_stores AS
            SELECT id, name, city, state, country, square_footage, open_date
            FROM stores
        """)

        # silver_returns
        cursor.execute("DROP TABLE IF EXISTS silver_returns")
        cursor.execute("""
            CREATE TABLE silver_returns AS
            SELECT id, transaction_id, product_id, quantity, refund_amount, return_reason, return_timestamp
            FROM returns
        """)

        # silver_inventory_movements
        cursor.execute("DROP TABLE IF EXISTS silver_inventory_movements")
        cursor.execute("""
            CREATE TABLE silver_inventory_movements AS
            SELECT id, product_id, store_id, movement_type, quantity, movement_timestamp
            FROM inventory_movements
        """)

        # gold_inventory_risk
        cursor.execute("DROP TABLE IF EXISTS gold_inventory_risk")
        cursor.execute("""
            CREATE TABLE gold_inventory_risk AS
            SELECT 
                s.name as store_name,
                p.name as product_name,
                ABS(RANDOM() % 45 + 5) as current_stock,
                ROUND(ABS(RANDOM() % 10 + 2.5), 1) as avg_daily_sales,
                ROUND(ABS(RANDOM() % 30 + 60.0), 1) as sell_through_pct,
                ROUND(ABS(RANDOM() % 14 + 1.2), 1) as days_of_supply,
                CASE 
                    WHEN ABS(RANDOM() % 10) < 3 THEN 'High Risk'
                    WHEN ABS(RANDOM() % 10) < 6 THEN 'Medium Risk'
                    ELSE 'Low Risk'
                END as risk_tier,
                CASE 
                    WHEN ABS(RANDOM() % 10) < 3 THEN 'Critical Restock Urgency'
                    WHEN ABS(RANDOM() % 10) < 6 THEN 'Reorder within 5 days'
                    ELSE 'Optimal Supply'
                END as reorder_suggestion
            FROM silver_products p
            CROSS JOIN silver_stores s
            LIMIT 15
        """)

        self.conn.commit()
        print("Silver & Gold tables synced successfully!")

def main():
    parser = argparse.ArgumentParser(description="Synthetic Retail Data Generator")
    parser.add_argument("--days", type=int, default=30, help="Days of history to generate")
    parser.add_argument("--db-url", type=str, default=None, help="Postgres DB URL connection string")
    parser.add_argument("--fallback", type=str, default=None, help="Path to SQLite fallback DB")
    args = parser.parse_args()

    generator = SyntheticDataGenerator(db_url=args.db_url, fallback_db_path=args.fallback)
    generator.create_schema()
    generator.run_generation(days_back=args.days)

if __name__ == "__main__":
    main()
