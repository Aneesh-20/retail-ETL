import os
import sys
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

# Base path for scripts
PROJECT_ROOT = "/opt/airflow" # Inside Airflow container, mounts the workspace root

default_args = {
    'owner': 'retail-data-platform',
    'depends_on_past': False,
    'start_date': datetime(2026, 7, 1),
    'email': ['data-alerts@retailplatform.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2),
    'execution_timeout': timedelta(minutes=15)
}

with DAG(
    'enterprise_retail_lakehouse_pipeline',
    default_args=default_args,
    description='Orchestrates Bronze ingestion, Silver cleaning, Warehouse synchronization, and ML Analytics refresh.',
    schedule_interval='@daily',
    catchup=False,
    tags=['lakehouse', 'pyspark', 'ml', 'retail']
) as dag:

    # 1. Generate new incremental transactions
    generate_data_task = BashOperator(
        task_id='generate_synthetic_data',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/generator/generate_data.py --days 1',
        env={**os.environ}
    )

    # 2. Ingest source tables into Bronze Delta Lake
    bronze_ingest_task = BashOperator(
        task_id='bronze_delta_ingest',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/ingestion/bronze_ingest.py',
        env={**os.environ}
    )

    # 3. Apply validation, casting, standardization & quarantine in Silver
    silver_clean_task = BashOperator(
        task_id='silver_delta_clean',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/ingestion/silver_clean.py',
        env={**os.environ}
    )

    # 4. Sync clean Silver data to PostgreSQL warehouse & SQLite fallback
    sync_warehouse_task = BashOperator(
        task_id='sync_silver_to_warehouse',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/warehouse/sync_to_pg.py',
        env={**os.environ}
    )

    # 5. Run ML Forecasting Engine
    run_forecaster_task = BashOperator(
        task_id='ml_sales_forecasting',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/analytics/forecaster.py',
        env={**os.environ}
    )

    # 6. Run Explainable Fraud Risk Scorer
    run_fraud_scorer_task = BashOperator(
        task_id='ml_fraud_risk_scoring',
        bash_command=f'python3.11 {PROJECT_ROOT}/src/analytics/fraud_scorer.py',
        env={**os.environ}
    )

    # Dependency Flow
    generate_data_task >> bronze_ingest_task >> silver_clean_task >> sync_warehouse_task >> [run_forecaster_task, run_fraud_scorer_task]
