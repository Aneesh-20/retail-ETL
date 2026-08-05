import os
import sys

# Ensure PySpark workers match current Python 3.11 executable environment
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

import uuid
import hashlib
from datetime import datetime
import pandas as pd

# Load dotenv to read config
from dotenv import load_dotenv
load_dotenv()

# PySpark imports
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, current_timestamp, udf, concat_ws, md5
from pyspark.sql.types import StringType

# Config paths
PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
BRONZE_DIR = os.path.join(PROJECT_ROOT, "lakehouse", "bronze")
os.makedirs(BRONZE_DIR, exist_ok=True)

def get_spark_session():
    # Configure Spark Session with Delta Lake support
    builder = SparkSession.builder \
        .appName("EnterpriseRetailBronzeIngest") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.1.0") \
        .config("spark.sql.warehouse.dir", "/tmp/spark-warehouse") \
        .config("spark.driver.memory", "2g") \
        .config("spark.sql.shuffle.partitions", "2") \
        .master("local[*]")

    # Check for S3/MinIO configurations
    s3_endpoint = os.getenv("AWS_ENDPOINT_URL")
    if s3_endpoint and "localhost" not in s3_endpoint:
        builder = builder \
            .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint) \
            .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID")) \
            .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY")) \
            .config("spark.hadoop.fs.s3a.path.style.access", "true") \
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")

    spark = builder.getOrCreate()
    return spark

def extract_source_data(table_name):
    """
    Extract data from PostgreSQL or fallback SQLite using SQLAlchemy/pandas to bypass JDBC jar dependencies
    """
    import sqlalchemy as sa
    db_url = os.getenv("SOURCE_DATABASE_URL")
    fallback_db = os.getenv("FALLBACK_DB_PATH", "./retail_fallback.db")
    
    try:
        engine = sa.create_engine(db_url, connect_args={"connect_timeout": 3})
        # Test connection
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        print(f"Reading '{table_name}' from PostgreSQL...")
        df = pd.read_sql_table(table_name, con=engine)
        return df
    except Exception as e:
        print(f"PostgreSQL connection failed ({e}). Reading '{table_name}' from SQLite: {fallback_db}...")
        engine = sa.create_engine(f"sqlite:///{fallback_db}")
        df = pd.read_sql_table(table_name, con=engine)
        return df

def ingest_table_to_bronze(spark, table_name, source_system, business_key_cols):
    print(f"\n--- Ingesting {table_name} to Bronze Delta ---")
    
    # 1. Extract
    pdf = extract_source_data(table_name)
    if pdf.empty:
        print(f"No records found in source table '{table_name}'. Skipping.")
        return
        
    print(f"Extracted {len(pdf)} rows.")

    # Convert timestamps/decimals in Pandas to strings to allow safe JSON packaging
    for col_name in pdf.columns:
        if pd.api.types.is_datetime64_any_dtype(pdf[col_name]):
            pdf[col_name] = pdf[col_name].dt.strftime('%Y-%m-%d %H:%M:%S')
        elif pd.api.types.is_numeric_dtype(pdf[col_name]) and not pd.api.types.is_integer_dtype(pdf[col_name]):
            pdf[col_name] = pdf[col_name].astype(str)

    # Convert DataFrame to JSON rows
    pdf['raw_payload'] = pdf.to_json(orient='records', lines=True).splitlines()
    
    # Create target spark dataframe with minimal schema
    spark_df = spark.createDataFrame(pdf[['id', 'raw_payload']])

    # 2. Add Ingestion Metadata
    run_id = str(uuid.uuid4())
    
    # Extract transaction_timestamp or generic timestamp for ordering
    # For POS/Orders, we can extract transaction_timestamp from raw_payload or use created_at
    # Let's write a simple UDF to parse timestamp or fallback
    def extract_time(payload):
        import json
        try:
            data = json.loads(payload)
            for t_col in ['transaction_timestamp', 'updated_at', 'created_at', 'ticket_timestamp', 'campaign_date']:
                if t_col in data and data[t_col]:
                    return data[t_col]
        except Exception:
            pass
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    extract_time_udf = udf(extract_time, StringType())
    
    # Build Bronze schema
    bronze_df = spark_df \
        .withColumn("source_system", lit(source_system)) \
        .withColumn("topic_table", lit(table_name)) \
        .withColumn("business_key", col("id")) \
        .withColumn("event_id", md5(concat_ws("-", lit(source_system), lit(table_name), col("id")))) \
        .withColumn("operation_type", lit("C")) \
        .withColumn("event_timestamp", extract_time_udf(col("raw_payload"))) \
        .withColumn("ingestion_timestamp", current_timestamp()) \
        .withColumn("schema_version", lit("1.0")) \
        .withColumn("kafka_partition", lit(0)) \
        .withColumn("kafka_offset", lit(0)) \
        .withColumn("pipeline_run_id", lit(run_id))
        
    # Pick final columns
    bronze_df = bronze_df.select(
        "event_id",
        "business_key",
        "raw_payload",
        "source_system",
        "topic_table",
        "operation_type",
        "event_timestamp",
        "ingestion_timestamp",
        "schema_version",
        "kafka_partition",
        "kafka_offset",
        "pipeline_run_id"
    )

    # 3. Load to local Delta Lake (or Parquet fallback)
    target_path = os.path.join(BRONZE_DIR, table_name)
    
    try:
        print(f"Writing to Bronze Delta at {target_path}...")
        bronze_df.write.format("delta").mode("overwrite").save(target_path)
    except Exception as e:
        print(f"Delta write failed: {e}. Falling back to Parquet format...")
        bronze_df.write.format("parquet").mode("overwrite").save(target_path)
    print(f"Successfully saved {table_name} to Bronze.")

def run_bronze_pipeline():
    spark = get_spark_session()
    
    # Map each source table to its system and identifier
    tables_to_ingest = [
        ("customers", "CRM", ["id"]),
        ("products", "INVENTORY", ["id"]),
        ("stores", "STORES", ["id"]),
        ("transactions", "POS_WEB_APP", ["id"]),
        ("returns", "RETURNS", ["id"]),
        ("inventory_movements", "INVENTORY", ["id"]),
        ("marketing_campaigns", "MARKETING", ["id"]),
        ("support_tickets", "CRM", ["id"])
    ]
    
    for table, system, keys in tables_to_ingest:
        try:
            ingest_table_to_bronze(spark, table, system, keys)
        except Exception as e:
            print(f"Failed to ingest {table}: {e}")
            
    spark.stop()

if __name__ == "__main__":
    run_bronze_pipeline()
