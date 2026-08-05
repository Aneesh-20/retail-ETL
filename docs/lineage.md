# Source-to-Target Data Lineage

This document traces the data flow from source transactional systems through the Lakehouse (Bronze & Silver) and Warehouse (Gold) layers to the API and Frontend applications.

---

## Data Flow Overview

```
Source DB (Postgres/SQLite)
     │
     ▼ (Debezium CDC / Ingestion Engine)
Kafka Topics / Batch Landing
     │
     ▼ (Spark Ingestion Pipeline)
Bronze Delta (Immutable Raw Storage)
     │
     ▼ (Spark Cleaning & Data Contracts Validation)
Silver Delta (Standardized, Cleaned, Deduplicated)
     │
     ▼ (Warehouse Sync Script)
PostgreSQL Warehouse (Public Schema)
     │
     ▼ (dbt Core Dimensional Models)
Gold Schema (Stars, SCD 2, Dimensions, Facts)
     │
     ▼
FastAPI Services & Machine Learning Forecasting / Fraud Models
     │
     ▼
Command Center Dashboard / Power BI
```

---

## Layer-by-Layer Mapping

### 1. Source System to Bronze
- **Source Tables**: `customers`, `products`, `stores`, `transactions`, `returns`, `inventory_movements`, `marketing_campaigns`, `support_tickets`.
- **Ingestion Mechanism**: Incremental CDC (via Debezium/Kafka) or micro-batch extract.
- **Bronze Target Schema**:
  - `event_id`: MD5 hash of `source_system` + `topic_table` + `id` (determines duplicate-free identity).
  - `business_key`: Original primary key from the source.
  - `raw_payload`: Complete JSON string of all source attributes.
  - `source_system`: Identifying string (e.g. `CRM`, `INVENTORY`).
  - `topic_table`: Original table/topic name.
  - `operation_type`: `C` (Create), `U` (Update), `D` (Delete).
  - `event_timestamp`: Extracted event source date.
  - `ingestion_timestamp`: Ingestion job processing timestamp.
  - `pipeline_run_id`: UUID mapping this run.

### 2. Bronze to Silver
- **Transformation Rules**:
  - **Timestamp Standardization**: `transaction_timestamp`, `created_at`, `updated_at`, `ticket_timestamp`, `resolution_timestamp` parsed into UTC datetime format.
  - **Money Normalization**: Cost, Price, Discount, and Refund values cast to `DECIMAL(18, 2)`.
  - **Value Trimming**: Strings trimmed of leading/trailing whitespaces.
  - **Enums**: Gender capitalized and mapped to `['M', 'F', 'OTHER', 'UNKNOWN']`. Channels capitalized and mapped to `['POS', 'WEBSITE', 'MOBILE_APP']`. States capitalized to two-letter abbreviations.
  - **Deduplication**: Grouped by `event_id`, picking the row with the latest `event_timestamp` / `ingestion_timestamp`.
  - **Data Contracts Enforcement**: Rows that fail nullability (`nullable: false`), enum constraints, or value limits (e.g., negative prices/quantities) are split off and redirected to `quarantine` tables.

### 3. Silver to Gold (dbt Core)
- **Staging (`ref('stg_*')`)**: Directly models individual Silver tables in Postgres, aliasing columns and providing standard types.
- **Dimensions (`ref('dim_*')`)**:
  - `dim_customer`: SCD Type 2 tracking `first_name`, `last_name`, `email`, `phone`, `gender`, `state` changes using `lead` to define active windows (`valid_from`, `valid_to`) and `is_current` indicators.
  - `dim_product`: SCD Type 2 tracking price, cost, and catalog descriptions.
  - `dim_campaign`: SCD Type 2 tracking campaign budgets and clicks.
  - `dim_store`: Stores directory.
  - `dim_date`: Static date dimension containing day, week, month, quarter, and weekend attributes.
  - `dim_channel` & `dim_promotion`: Extracted transaction features.
- **Facts (`ref('fact_*')`)**:
  - `fact_sales_line`: Joins transactional records to SCD Type 2 dimensions by evaluating event timestamps against dimension validity bounds. Computes financial metrics (net sales, gross margin, cost).
  - `fact_return_line`: Joins return details to product keys.
  - `fact_inventory_movement`: Detail logs of inventory additions/sales.
  - `fact_inventory_daily_snapshot`: Generated cross-product grid evaluating cumulative sales vs restocks to resolve stock-on-hand per store per product per day.
  - `fact_support_ticket`: Logs support tickets, customer keys, and computes resolution hours.
  - `fact_customer_activity`: Unions purchases, returns, and support cases into a chronological engagement timeline.

### 4. Serving (FastAPI & Power BI)
- **FastAPI**: Pulls metric queries from fact tables (such as `fact_sales_forecast` and `fact_fraud_queue`) to serve dashboards.
- **Power BI Semantic Models**: Consumes Gold star schemas directly from PostgreSQL tables.
