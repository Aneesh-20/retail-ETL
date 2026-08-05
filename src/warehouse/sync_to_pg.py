import os
import sys
import pandas as pd

# Load dotenv
from dotenv import load_dotenv
load_dotenv()

from pyspark.sql import SparkSession

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
SILVER_DIR = os.path.join(PROJECT_ROOT, "lakehouse", "silver")

def get_spark_session():
    return SparkSession.builder \
        .appName("SyncSilverToWarehouse") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.1.0") \
        .config("spark.driver.memory", "2g") \
        .config("spark.sql.shuffle.partitions", "2") \
        .master("local[*]") \
        .getOrCreate()

def sync_table_to_dbs(spark, table_name):
    silver_path = os.path.join(SILVER_DIR, table_name)
    if not os.path.exists(silver_path):
        print(f"Silver Delta table not found for {table_name}. Skipping.")
        return

    # 1. Read clean Silver data (Delta or Parquet fallback)
    try:
        silver_df = spark.read.format("delta").load(silver_path)
    except Exception:
        print("Delta read failed. Reading from Parquet format...")
        silver_df = spark.read.format("parquet").load(silver_path)
        
    count = silver_df.count()
    print(f"\nSyncing clean '{table_name}' ({count} rows) to warehouse...")

    # 2. Convert to Pandas
    pdf = silver_df.toPandas()
    
    # 3. Write to PostgreSQL (Warehouse)
    db_url = os.getenv("DATABASE_URL")
    import sqlalchemy as sa
    
    # Clean datetime timezone representations & Decimals for relational DB write
    import decimal
    for col_name in pdf.columns:
        if pd.api.types.is_datetime64_any_dtype(pdf[col_name]):
            pdf[col_name] = pd.to_datetime(pdf[col_name]).dt.tz_localize(None)
        elif pdf[col_name].dtype == 'object':
            pdf[col_name] = pdf[col_name].apply(lambda x: float(x) if isinstance(x, decimal.Decimal) else x)

    postgres_success = False
    try:
        engine = sa.create_engine(db_url, connect_args={"connect_timeout": 3})
        # Test connection
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        
        # Write to postgres
        print("Writing to PostgreSQL database...")
        # Write under silver prefix or as tables directly (dbt will read these as sources)
        pdf.to_sql(f"silver_{table_name}", con=engine, if_exists="replace", index=False)
        postgres_success = True
        print(f"Successfully synced '{table_name}' to PostgreSQL as 'silver_{table_name}'.")
    except Exception as e:
        print(f"Could not sync '{table_name}' to PostgreSQL: {e}")

    # 4. Write to SQLite fallback (so FastAPI backend can run independently)
    fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
    try:
        sqlite_engine = sa.create_engine(f"sqlite:///{fallback_db}")
        print(f"Writing to SQLite fallback database: {fallback_db}")
        pdf.to_sql(f"silver_{table_name}", con=sqlite_engine, if_exists="replace", index=False)
        print(f"Successfully synced '{table_name}' to SQLite as 'silver_{table_name}'.")
    except Exception as e:
        print(f"Failed to write to SQLite: {e}")

def run_sync_pipeline():
    spark = get_spark_session()
    
    tables = [
        "customers",
        "products",
        "stores",
        "transactions",
        "returns",
        "inventory_movements",
        "marketing_campaigns",
        "support_tickets"
    ]
    
    for t in tables:
        sync_table_to_dbs(spark, t)
        
    spark.stop()

if __name__ == "__main__":
    run_sync_pipeline()
