import os
import sys

# Ensure PySpark workers match current Python 3.11 executable environment
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

import yaml
import json
from datetime import datetime
import pandas as pd

# Load dotenv
from dotenv import load_dotenv
load_dotenv()

from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import col, from_json, current_timestamp, lit, trim, upper, to_timestamp, row_number, desc
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, DecimalType, TimestampType
from pyspark.sql.window import Window

PROJECT_ROOT = "/Users/aneeshnaren/Documents/retail_lakehouse"
BRONZE_DIR = os.path.join(PROJECT_ROOT, "lakehouse", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "lakehouse", "silver")
QUARANTINE_DIR = os.path.join(SILVER_DIR, "quarantine")

os.makedirs(SILVER_DIR, exist_ok=True)
os.makedirs(QUARANTINE_DIR, exist_ok=True)

# 1. Load Data Contracts Configuration
def load_contracts():
    contract_path = os.path.join(PROJECT_ROOT, "config", "data_contracts.yaml")
    if os.path.exists(contract_path):
        with open(contract_path, 'r') as f:
            return yaml.safe_load(f).get("contracts", {})
    return {}

# Define Spark Ingestion session
def get_spark_session():
    return SparkSession.builder \
        .appName("EnterpriseRetailSilverClean") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.jars.packages", "io.delta:delta-spark_2.12:3.1.0") \
        .config("spark.driver.memory", "2g") \
        .config("spark.sql.shuffle.partitions", "2") \
        .master("local[*]") \
        .getOrCreate()

def get_spark_schema_from_contract(contract_cols):
    fields = []
    for col_name, rules in contract_cols.items():
        col_type = rules.get("type", "string")
        if col_type == "integer":
            spark_type = IntegerType()
        elif col_type == "decimal":
            spark_type = DecimalType(18, 2)
        elif col_type == "double":
            spark_type = DoubleType()
        else:
            spark_type = StringType() # We keep timestamps/dates as string first to parse explicitly
        fields.append(StructField(col_name, spark_type, nullable=True)) # Allow nullable in parse schema, enforce in checks
    return StructType(fields)

def process_table_silver(spark, table_name, contract):
    print(f"\n===========================================")
    print(f"Processing Silver Table: {table_name}")
    print(f"===========================================")
    
    bronze_path = os.path.join(BRONZE_DIR, table_name)
    if not os.path.exists(bronze_path):
        print(f"Bronze Delta path does not exist for {table_name}. Skipping.")
        return

    # 1. Read Bronze Table (Delta or Parquet fallback)
    try:
        bronze_df = spark.read.format("delta").load(bronze_path)
    except Exception:
        print("Delta read failed. Reading Bronze from Parquet format...")
        try:
            bronze_df = spark.read.format("parquet").load(bronze_path)
        except Exception as pe:
            print(f"Skipping {table_name}: Bronze Parquet read failed or directory empty ({pe}).")
            return
        
    total_bronze_count = bronze_df.count()
    print(f"Read {total_bronze_count} rows from Bronze.")
    
    if total_bronze_count == 0:
        print("Bronze table is empty. Skipping.")
        return

    # 2. Extract columns and parse json payload
    columns = contract.get("columns", {})
    json_schema = get_spark_schema_from_contract(columns)
    
    parsed_df = bronze_df.withColumn("data", from_json(col("raw_payload"), json_schema))
    
    # Select individual parsed columns along with bronze metadata
    select_exprs = [
        col("event_id"),
        col("operation_type"),
        col("event_timestamp"),
        col("ingestion_timestamp").alias("bronze_ingestion_time"),
        col("pipeline_run_id").alias("bronze_run_id")
    ]
    for c in columns.keys():
        select_exprs.append(col(f"data.{c}").alias(c))
        
    flat_df = parsed_df.select(*select_exprs)

    # 3. Apply Transformations & Cleanings
    # Normalizing dates/timestamps, string trims
    clean_df = flat_df
    
    # Apply type conversions and standardizations
    for col_name, rules in columns.items():
        c_type = rules.get("type")
        
        # String standardization
        if c_type == "string":
            clean_df = clean_df.withColumn(col_name, trim(col(col_name)))
            
            # Gender standardisation
            if col_name == "gender":
                clean_df = clean_df.withColumn(
                    col_name,
                    upper(col(col_name))
                )
                
            # State code standardization (e.g. UPPER)
            if col_name == "state":
                clean_df = clean_df.withColumn(col_name, upper(col(col_name)))

        # Normalize dates/timestamps to UTC datetime
        if col_name in ["transaction_timestamp", "created_at", "updated_at", "ticket_timestamp", "resolution_timestamp", "birth_date"]:
            # Standardize date format to Timestamp
            clean_df = clean_df.withColumn(col_name, to_timestamp(col(col_name)))

    # 4. Check Contracts & Generate Quarantine Violations
    # Build validation rules
    validations = []
    
    for col_name, rules in columns.items():
        # Null check
        if not rules.get("nullable", True):
            validations.append((col(col_name).isNull(), f"{col_name} is null"))
            
        # Enum value check
        if "accepted_values" in rules:
            accepted = rules["accepted_values"]
            validations.append((~col(col_name).isin(accepted) & col(col_name).isNotNull(), f"{col_name} not in accepted values"))
            
        # Min value check
        if "min_value" in rules:
            min_val = rules["min_value"]
            validations.append((col(col_name) < min_val, f"{col_name} is below min value {min_val}"))
            
        # Length check
        if "length" in rules:
            length = rules["length"]
            # Length works on string length
            from pyspark.sql.functions import length as spark_len
            validations.append((spark_len(col(col_name)) != length, f"{col_name} length does not equal {length}"))

    # Apply validation logic to split clean and quarantined
    quarantine_conditions = None
    for cond, reason in validations:
        # Mark row with reason if condition is true
        from pyspark.sql.functions import when
        if quarantine_conditions is None:
            quarantine_conditions = when(cond, reason)
        else:
            quarantine_conditions = quarantine_conditions.when(cond, reason)
            
    if quarantine_conditions is not None:
        quarantine_conditions = quarantine_conditions.otherwise(lit(None))
        df_validated = clean_df.withColumn("quarantine_reason", quarantine_conditions)
    else:
        df_validated = clean_df.withColumn("quarantine_reason", lit(None))

    # Split rows
    quarantine_rows = df_validated.filter(col("quarantine_reason").isNotNull())
    valid_rows = df_validated.filter(col("quarantine_reason").isNull()).drop("quarantine_reason")

    # 5. Deduplicate clean records (Event-time deduplication)
    # Deduplicate by event_id, keep latest by event_timestamp (or ingestion time)
    # This prevents late-arriving updates or duplicates from creating separate entries
    window_spec = Window.partitionBy("event_id").orderBy(desc("event_timestamp"), desc("bronze_ingestion_time"))
    valid_dedup_rows = valid_rows \
        .withColumn("rn", row_number().over(window_spec)) \
        .filter(col("rn") == 1) \
        .drop("rn")

    # 6. Save Quarantine
    quarantine_count = quarantine_rows.count()
    if quarantine_count > 0:
        quarantine_path = os.path.join(QUARANTINE_DIR, table_name)
        print(f"Quarantined {quarantine_count} invalid records to: {quarantine_path}")
        try:
            quarantine_rows.write.format("delta").mode("append").save(quarantine_path)
        except Exception:
            quarantine_rows.write.format("parquet").mode("append").save(quarantine_path)

    # 7. Save Clean Silver Data
    final_clean_count = valid_dedup_rows.count()
    silver_table_path = os.path.join(SILVER_DIR, table_name)
    print(f"Saving {final_clean_count} deduplicated clean records to: {silver_table_path}")
    try:
        valid_dedup_rows.write.format("delta").mode("overwrite").save(silver_table_path)
    except Exception:
        valid_dedup_rows.write.format("parquet").mode("overwrite").save(silver_table_path)
    
    # 8. Data Quality Audits & Reconciliation
    # Reconcile counts: Bronze = Clean Silver + Quarantined + Deduplicated duplicates
    duplicate_count = valid_rows.count() - final_clean_count
    print(f"Reconciliation Report for '{table_name}':")
    print(f"  - Raw Bronze Count: {total_bronze_count}")
    print(f"  - Clean Silver Count: {final_clean_count}")
    print(f"  - Quarantined Count: {quarantine_count}")
    print(f"  - Duplicates Removed: {duplicate_count}")
    print(f"  - Total Accounted: {final_clean_count + quarantine_count + duplicate_count}")
    reconciled = (total_bronze_count == (final_clean_count + quarantine_count + duplicate_count))
    print(f"  - Reconciled: {reconciled}")

    # Write audit log to local JSON for FastAPI to display pipeline quality logs
    log_audit(table_name, total_bronze_count, final_clean_count, quarantine_count, duplicate_count, reconciled)

def log_audit(table, bronze_cnt, silver_cnt, quarantine_cnt, dup_cnt, reconciled):
    audit_file = os.path.join(SILVER_DIR, "dq_audit_log.json")
    audit_data = []
    
    if os.path.exists(audit_file):
        try:
            with open(audit_file, "r") as f:
                audit_data = json.load(f)
        except Exception:
            pass
            
    audit_entry = {
        "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "table_name": table,
        "bronze_count": bronze_cnt,
        "silver_count": silver_cnt,
        "quarantine_count": quarantine_cnt,
        "duplicate_count": dup_cnt,
        "reconciled": reconciled,
        "quality_score": round((silver_cnt / bronze_cnt) * 100, 2) if bronze_cnt > 0 else 100.0
    }
    
    # Update or append
    audit_data = [e for e in audit_data if e["table_name"] != table]
    audit_data.append(audit_entry)
    
    with open(audit_file, "w") as f:
        json.dump(audit_data, f, indent=2)

def run_silver_pipeline():
    spark = get_spark_session()
    contracts = load_contracts()
    
    # We will process each table defined in our data contract.
    # For tables not explicitly in YAML, we can add default contracts here to ensure full pipeline coverage.
    for table_name in ["customers", "products", "transactions"]:
        if table_name in contracts:
            process_table_silver(spark, table_name, contracts[table_name])
            
    # For returns, inventory, support, campaigns, let's create dynamic contracts if not defined
    default_contracts = {
        "stores": {
            "columns": {
                "id": {"type": "string", "nullable": False},
                "name": {"type": "string", "nullable": False},
                "city": {"type": "string", "nullable": False},
                "state": {"type": "string", "nullable": False},
                "country": {"type": "string", "nullable": False}
            }
        },
        "returns": {
            "columns": {
                "id": {"type": "string", "nullable": False},
                "transaction_id": {"type": "string", "nullable": False},
                "product_id": {"type": "string", "nullable": False},
                "quantity": {"type": "integer", "nullable": False, "min_value": 1},
                "refund_amount": {"type": "decimal", "nullable": False, "min_value": 0.0}
            }
        },
        "inventory_movements": {
            "columns": {
                "id": {"type": "string", "nullable": False},
                "product_id": {"type": "string", "nullable": False},
                "store_id": {"type": "string", "nullable": False},
                "movement_type": {"type": "string", "nullable": False, "accepted_values": ["RESTOCK", "DAMAGE", "SALE", "RETURN"]},
                "quantity": {"type": "integer", "nullable": False}
            }
        },
        "marketing_campaigns": {
            "columns": {
                "id": {"type": "string", "nullable": False},
                "campaign_name": {"type": "string", "nullable": False},
                "channel": {"type": "string", "nullable": False},
                "cost": {"type": "decimal", "nullable": False, "min_value": 0.0}
            }
        },
        "support_tickets": {
            "columns": {
                "id": {"type": "string", "nullable": False},
                "customer_id": {"type": "string", "nullable": False},
                "issue_category": {"type": "string", "nullable": False},
                "status": {"type": "string", "nullable": False, "accepted_values": ["OPEN", "IN_PROGRESS", "RESOLVED"]}
            }
        }
    }
    
    for table_name, contract in default_contracts.items():
        if table_name not in contracts:
            process_table_silver(spark, table_name, contract)

    spark.stop()

if __name__ == "__main__":
    run_silver_pipeline()
