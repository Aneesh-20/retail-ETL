# Relational Data Models (Gold Warehouse Schema)

This document details the dimensional star schema implemented in the Gold Warehouse layer (`retail_warehouse` database, public schema).

---

## Star Schema Overview

```
                 ┌──────────────────┐
                 │     dim_date     │
                 └────────┬─────────┘
                          │
 ┌────────────────┐       │ (date_day)      ┌────────────────┐
 │  dim_customer  ├───────┼─────────────────┤   dim_product  │
 └───────┬────────┘       │                 └────────┬───────┘
         │                ▼                          │
         │       ┌──────────────────┐                │
         └──────►│  fact_sales_line  │◄───────────────┘
                 └────────┬─────────┘
                          │
 ┌────────────────┐       │                 ┌────────────────┐
 │    dim_store   ├───────┼─────────────────┤  dim_promotion │
 └────────────────┘       │                 └────────────────┘
                          ▼
                 ┌──────────────────┐
                 │   dim_channel    │
                 └──────────────────┘
```

---

## Dimension Tables

### 1. `dim_date`
- `date_day` (DATE, Primary Key) - Date value calendar key.
- `year` (INTEGER) - Calendar year.
- `month` (INTEGER) - Month number (1-12).
- `month_name` (VARCHAR) - Text month representation (e.g. `July`).
- `day` (INTEGER) - Day of the month.
- `day_of_week` (INTEGER) - Day Index (1 = Monday, 7 = Sunday).
- `day_name` (VARCHAR) - Text day representation (e.g. `Tuesday`).
- `quarter` (INTEGER) - Quarter (1-4).
- `is_weekend` (BOOLEAN) - Indicator for Saturday/Sunday.

### 2. `dim_customer` (SCD Type 2)
- `customer_key` (VARCHAR(32), Primary Key) - MD5 surrogate key of `customer_id` + `valid_from`.
- `customer_id` (VARCHAR(100), Natural Business Key) - CRM client unique identifier.
- `first_name` (VARCHAR(100)) - Customer first name (PII).
- `last_name` (VARCHAR(100)) - Customer last name (PII).
- `email` (VARCHAR(100)) - Contact email address (PII).
- `phone` (VARCHAR(50)) - Contact phone number (PII).
- `gender` (VARCHAR(20)) - Standardized gender code.
- `state` (VARCHAR(2)) - Customer state.
- `birth_date` (DATE) - Birth date (PII).
- `valid_from` (TIMESTAMP) - Dimension slice start timestamp.
- `valid_to` (TIMESTAMP) - Dimension slice end timestamp (falls back to `9999-12-31`).
- `is_current` (BOOLEAN) - True if this represents the current customer profile.

### 3. `dim_product` (SCD Type 2)
- `product_key` (VARCHAR(32), Primary Key) - MD5 surrogate key of `product_id` + `valid_from`.
- `product_id` (VARCHAR(100)) - Inventory catalog product identifier.
- `sku` (VARCHAR(50)) - Product stock keeping unit code.
- `name` (VARCHAR(150)) - Catalog display name.
- `category` (VARCHAR(100)) - Product category group.
- `price` (DECIMAL(18, 2)) - Product retail price.
- `cost` (DECIMAL(18, 2)) - Product sourcing cost.
- `valid_from` (TIMESTAMP) - Start date slice.
- `valid_to` (TIMESTAMP) - End date slice.
- `is_current` (BOOLEAN) - Current indicator.

### 4. `dim_store`
- `store_key` (VARCHAR(32), Primary Key) - MD5 surrogate key.
- `store_id` (VARCHAR(100)) - Store location identifier.
- `store_name` (VARCHAR(150)) - Branch display name.
- `city` (VARCHAR(100)) - Location city.
- `state` (VARCHAR(2)) - Location state.
- `country` (VARCHAR(100)) - Location country.

### 5. `dim_channel`
- `channel_key` (VARCHAR(32), Primary Key) - MD5 hash.
- `channel_name` (VARCHAR(50)) - Sales channel name (`POS`, `WEBSITE`, `MOBILE_APP`).

### 6. `dim_campaign` (SCD Type 2)
- `campaign_key` (VARCHAR(32), Primary Key) - MD5 surrogate key.
- `campaign_id` (VARCHAR(100)) - Campaign ID.
- `campaign_name` (VARCHAR(150)) - Campaign display name.
- `channel` (VARCHAR(50)) - Marketing channel.
- `valid_from` (DATE) - Start date.
- `valid_to` (DATE) - End date.
- `is_current` (BOOLEAN) - Current status.

### 7. `dim_promotion`
- `promotion_key` (VARCHAR(32), Primary Key) - MD5 hash.
- `promotion_id` (VARCHAR(50)) - Promotion identifier.
- `promotion_name` (VARCHAR(100)) - Friendly promotion tier.
- `discount_rate` (DECIMAL(5, 2)) - Applied average discount percentage.

---

## Fact Tables

### 1. `fact_sales_line`
- `transaction_line_id` (VARCHAR(100), Primary Key) - Line item ID.
- `transaction_id` (VARCHAR(100)) - Parent order transaction ID.
- `customer_key` (VARCHAR(32)) - FK to `dim_customer` (resolved by event time).
- `product_key` (VARCHAR(32)) - FK to `dim_product` (resolved by event time).
- `store_key` (VARCHAR(32)) - FK to `dim_store`.
- `channel_key` (VARCHAR(32)) - FK to `dim_channel`.
- `promotion_key` (VARCHAR(32)) - FK to `dim_promotion`.
- `date_day` (DATE) - FK to `dim_date`.
- `quantity` (INTEGER) - Order quantity.
- `unit_price` (DECIMAL(18, 2)) - Item transaction price.
- `discount` (DECIMAL(18, 2)) - Applied line discount.
- `net_sales` (DECIMAL(18, 2)) - Computed net revenue: `(quantity * unit_price) - discount`.
- `total_cost` (DECIMAL(18, 2)) - Sourcing cost: `quantity * cost`.
- `gross_margin` (DECIMAL(18, 2)) - Gross margin: `net_sales - total_cost`.
- `transaction_timestamp` (TIMESTAMP) - Ingestion ordering anchor.

### 2. `fact_return_line`
- `return_id` (VARCHAR(100), Primary Key) - Return unique ID.
- `transaction_id` (VARCHAR(100)) - Transaction ID of purchase.
- `product_key` (VARCHAR(32)) - FK to product dimension.
- `date_day` (DATE) - FK to date.
- `quantity` (INTEGER) - Returned units count.
- `refund_amount` (DECIMAL(18, 2)) - Refund amount returned.
- `return_reason` (VARCHAR(255)) - Reason description.

### 3. `fact_inventory_daily_snapshot`
- `snapshot_key` (VARCHAR(32), Primary Key) - MD5 of `date_day` + `product_key` + `store_key`.
- `date_day` (DATE) - FK to date.
- `product_key` (VARCHAR(32)) - FK to product.
- `store_key` (VARCHAR(32)) - FK to store.
- `stock_on_hand` (INTEGER) - Cumulative inventory units in stock.

### 4. `fact_inventory_movement`
- `movement_id` (VARCHAR(100), Primary Key) - Movement ID.
- `product_key` (VARCHAR(32)) - FK to product.
- `store_key` (VARCHAR(32)) - FK to store.
- `movement_type` (VARCHAR(50)) - Restock, damage, sale, return.
- `quantity` (INTEGER) - Adjust quantity (positive or negative).
- `date_day` (DATE) - FK to date.

### 5. `fact_marketing_daily`
- `campaign_id` (VARCHAR(100)) - Campaign natural key.
- `campaign_key` (VARCHAR(32)) - FK to campaign dimension.
- `date_day` (DATE) - FK to date.
- `cost` (DECIMAL(18, 2)) - Daily marketing spend.
- `impressions` (INTEGER) - Daily ad views.
- `clicks` (INTEGER) - Daily click clicks.
- `conversions` (INTEGER) - Daily conversions.
- `click_to_conv_rate` (DECIMAL(18, 4)) - Click to conversion ratio.

### 6. `fact_support_ticket`
- `ticket_id` (VARCHAR(100), Primary Key) - Ticket ID.
- `customer_key` (VARCHAR(32)) - FK to customer dimension.
- `date_day` (DATE) - FK to date.
- `issue_category` (VARCHAR(100)) - Support category.
- `status` (VARCHAR(50)) - Open, in-progress, resolved.
- `priority` (VARCHAR(50)) - Low, medium, high.
- `ticket_timestamp` (TIMESTAMP) - Ticket creation.
- `resolution_timestamp` (TIMESTAMP) - Ticket closing.

### 7. `fact_customer_activity`
- `activity_key` (VARCHAR(32), Primary Key) - Unique MD5.
- `customer_key` (VARCHAR(32)) - FK to customer.
- `activity_timestamp` (TIMESTAMP) - Exact action datetime.
- `date_day` (DATE) - FK to date.
- `activity_type` (VARCHAR(50)) - Purchase, return, support.
- `activity_details` (VARCHAR(255)) - Description.
