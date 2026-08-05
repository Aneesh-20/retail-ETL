# Enterprise Retail Lakehouse Command Center Platform

An end-to-end, production-grade Retail Lakehouse Platform built on a modern data architecture. The platform transforms messy, duplicated, and late-arriving POS, website, CRM, inventory, and support data into gold-standard business aggregates, ML forecasts, and fraud alerts.

---

## Architecture Flow

```
POS / Web / Mobile App / CRM / Inventory / Marketing
                  │
                  ▼ (Transactional Database)
             PostgreSQL Source DB (Logical Replication Enabled)
                  │
                  ▼ (Debezium Postgres CDC)
             Apache Kafka / Kafka Connect
                  │
                  ▼ (Spark Structured Streaming / Micro-Batch)
             Bronze Delta Lake (Immutable Raw Payload & Ingestion Metadata)
                  │
                  ▼ (Spark Cleaning & Schema Contract Validation)
             Silver Delta Lake (Normalizations, Deduplications, Clean, DLQ)
                  │
                  ▼ (Warehouse Synchronizer)
             PostgreSQL Warehouse / SQLite Fallback
                  │
                  ▼ (dbt Core Models)
             Gold Marts Schema (Dimensions, Facts, SCD Type 2)
                  │
                  ▼ (Forecasting & Fraud ML Engines)
             Gold ML Tables (Predictions, Explainable Risk Scores)
                  │
                  ▼
             FastAPI Serving Engine
                  │
                  ▼
             Command Center Responsive Dashboard / Power BI
```

---

## Technology Stack

- **Data Engineering**: Python 3.11, PySpark, Delta Lake
- **CDC & Streaming**: PostgreSQL, Apache Kafka, Kafka Connect, Debezium CDC
- **Data Warehousing & Transformation**: dbt Core, PostgreSQL
- **Orchestration**: Apache Airflow
- **Serving & Machine Learning**: FastAPI, Scikit-learn (Ridge Regression), Pandas, SQLAlchemy
- **Aesthetics & Frontend**: Vanilla HTML5, CSS3 Grid/Flexbox, Chart.js, Lucide Icons
- **Infrastructure**: Docker Compose, MinIO S3

---

## Directory Structure

- `src/generator/`: Synthetic retail transactional data generator (includes returns, updates, late arrivals, duplicates, and fraud sequences).
- `src/ingestion/`: Ingest pipelines (Bronze immutable ingestion, Silver schema contract validations, and DLQ quarantine split).
- `src/warehouse/`: Syncing clean Silver data to database, dbt Core models, intermediate transformations, and Gold marts (SCD Type 2 dimensions and facts).
- `src/analytics/`: ML engines for 7-day Ridge sales forecasting and explainable fraud risk scoring.
- `src/backend/`: FastAPI serving application.
- `src/frontend/`: Responsive command center dashboard UI.
- `dags/`: Airflow DAG orchestrator.
- `tests/`: Pytest pipelines and unit testing suites.
- `docs/`: Design lineage, dimensional diagrams, PII protection policy, and Power BI semantic models instructions.

---

## Setup & Execution (Standalone Local Mode)

For ease of local testing and validation without provisioning container resources, the entire platform runs out-of-the-box in **local fallback mode** using Python 3.11:

### 1. Configure the Environment
Ensure Python 3.11 is active, and install all dependencies:
```bash
pip3.11 install -r requirements.txt
cp .env.example .env
```

### 2. Generate Source Database (Auto-Seed)
Run the generator to create `retail_fallback.db` populated with 30 days of transactions, customer profiles, support tickets, and intentional anomalies:
```bash
python3.11 src/generator/generate_data.py --days 30
```

### 3. Run Ingestion Pipelines
Run Bronze Ingestion (Raw landing) and Silver Ingestion (Cleaning & contract verification):
```bash
export PYSPARK_PYTHON=python3.11
export PYSPARK_DRIVER_PYTHON=python3.11
python3.11 src/ingestion/bronze_ingest.py
python3.11 src/ingestion/silver_clean.py
```

### 4. Sync & Execute Analytics Engines
Sync clean silver data to the relational analytics DB and run the forecasting and fraud scoring ML models:
```bash
python3.11 src/warehouse/sync_to_pg.py
python3.11 src/analytics/forecaster.py
python3.11 src/analytics/fraud_scorer.py
```

### 5. Launch FastAPI Backend
```bash
python3.11 src/backend/main.py
```
*API docs will be available at: `http://localhost:8000/docs`*

### 6. Open Command Center UI
Double-click `src/frontend/index.html` or host it with a static web server:
```bash
cd src/frontend && python3.11 -m http.server 3000
```
*Open `http://localhost:3000` in your web browser.*

---

## Setup & Execution (Docker Compose Mode)

To run the full stack containing PostgreSQL, MinIO, Kafka, Kafka Connect, Airflow, and FastAPI backend:

```bash
# Build and boot containers
docker-compose up -d --build
```

### Service Directory URL Reference
- **FastAPI Command Center API**: `http://localhost:8000/docs`
- **Dashboard Command Center**: `http://localhost:3000` (or local file index.html)
- **Apache Airflow Dashboard**: `http://localhost:8080` (credentials: `admin`/`admin`)
- **MinIO Console**: `http://localhost:9001` (credentials: `minioadmin`/`minioadmin`)
- **Kafka Connect API**: `http://localhost:8083`

---

## Five-Minute Demo Walkthrough

1. **Access Command Center**: Navigate to `http://localhost:3000` to load the **Overview dashboard**. You will see total gross sales, margins, return rates, active customers, and a 98% data quality score.
2. **Sales Forecasting**: Click **Sales & Forecast** in the sidebar. You'll see historical sales lines plotted alongside the Ridge forecasting model predictions for the next 7 days, complete with evaluation metrics (MAE, RMSE, WAPE).
3. **Data Quality & DLQ Quarantine**: Go to **Pipeline Health**. You will see table rows processed, duplicates removed, and reconciliation states. Under **Active Contract Incidents**, check the quarantined records details that failed contract validations.
4. **Fraud Risk Review**: Click **Fraud Queue**. Examine transactions flagged as High or Medium risk. You will see an explainability factor (e.g. "High velocity: 5 purchases in 1 hour"). Click **Approve** or **Dismiss** to update its review status in the database.
5. **Inventory Health**: Go to **Inventory Alerts**. Inspect products flagged as High stockout risk (Days of Supply < 5) and view their reorder quantities. Click **Export CSV** to download the operational alert sheet.

---

## Known Constraints & Design Limitations
- **Kafka Connectivity**: Standalone execution uses fallback SQLite databases which bypasses streaming Kafka Connect CDC. To run CDC, boot Docker Compose and activate Debezium connectors via the REST API.
- **dbt PostgreSQL Requirement**: The dbt transformations run against PostgreSQL. During local SQLite execution, the FastAPI backend computes the dimensional facts directly on the clean silver data in memory via Pandas, achieving identical output schemas.
