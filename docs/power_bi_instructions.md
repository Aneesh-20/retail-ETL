# Power BI Semantic Model & Build Instructions

This document provides technical instructions for configuring the Enterprise Retail Semantic Model and analytical report dashboard in Power BI.

---

## 1. Data Connection

1. **Connector**: PostgreSQL Database.
2. **Server**: `<postgresql-host>:<port>`
3. **Database**: `retail_warehouse`
4. **Authentication**: Database credentials (configured via secure enterprise credentials gateway).
5. **Storage Mode**: Import (recommended for sub-second visual performance) or DirectQuery.

---

## 2. Relationship Model (Star Schema)

Configure the following relationships in the Power BI Model View. All relationships should be **1-to-many (*)** from the Dimension to the Fact, with **Single** cross-filter direction:

| From Table (Dimension) | From Key | To Table (Fact) | To Key | Active |
|---|---|---|---|---|
| `dim_date` | `date_day` | `fact_sales_line` | `date_day` | Yes |
| `dim_customer` | `customer_key` | `fact_sales_line` | `customer_key` | Yes |
| `dim_product` | `product_key` | `fact_sales_line` | `product_key` | Yes |
| `dim_store` | `store_key` | `fact_sales_line` | `store_key` | Yes |
| `dim_channel` | `channel_key` | `fact_sales_line` | `channel_key` | Yes |
| `dim_promotion` | `promotion_key` | `fact_sales_line` | `promotion_key` | Yes |
| `dim_date` | `date_day` | `fact_return_line` | `date_day` | Yes |
| `dim_product` | `product_key` | `fact_return_line` | `product_key` | Yes |
| `dim_date` | `date_day` | `fact_inventory_daily_snapshot` | `date_day` | Yes |
| `dim_product` | `product_key` | `fact_inventory_daily_snapshot` | `product_key` | Yes |
| `dim_store` | `store_key` | `fact_inventory_daily_snapshot` | `store_key` | Yes |
| `dim_date` | `date_day` | `fact_marketing_daily` | `date_day` | Yes |
| `dim_campaign` | `campaign_key` | `fact_marketing_daily` | `campaign_key` | Yes |
| `dim_date` | `date_day` | `fact_support_ticket` | `date_day` | Yes |
| `dim_customer` | `customer_key` | `fact_support_ticket` | `customer_key` | Yes |

---

## 3. DAX Calculated Measures

Create the following measures in the `fact_sales_line` and related tables:

### Gross Revenue
```dax
Total Revenue = SUM(fact_sales_line[net_sales])
```

### Cost of Goods Sold (COGS)
```dax
Total Cost = SUM(fact_sales_line[total_cost])
```

### Gross Margin %
```dax
Gross Margin % = 
DIVIDE(
    [Total Revenue] - [Total Cost],
    [Total Revenue],
    0
)
```

### Return Value
```dax
Total Refund = SUM(fact_return_line[refund_amount])
```

### Returns Rate %
```dax
Return Rate % = 
DIVIDE(
    [Total Refund],
    [Total Revenue],
    0
)
```

### Sales Forecast (Ridge Model Overlay)
```dax
Forecast Sales = SUM(fact_sales_forecast[forecast_sales])
```

### Forecast Variance
```dax
Forecast Variance = [Total Revenue] - [Forecast Sales]
```

### Stock-on-Hand (SOH)
```dax
Current Stock = 
CALCULATE(
    SUM(fact_inventory_daily_snapshot[stock_on_hand]),
    LASTDATE(dim_date[date_day])
)
```

---

## 4. Visual Layout Specifications

### Dashboard Page 1: Executive Overview
- **KPI Card Strip**: Total Revenue, Gross Margin %, Return Rate %, Active Customers, DQ Score.
- **Main Line Chart**: X-Axis = `dim_date[date_day]`, Values = `[Total Revenue]` vs. `[Forecast Sales]`.
- **Donut Chart**: Legend = `dim_channel[channel_name]`, Values = `[Total Revenue]`.
- **Bar Chart**: Y-Axis = `dim_customer[segment]`, Values = Distinct Customer Count.

### Dashboard Page 2: Operations & Quality
- **Table Grid**: Inventory Risk. Group by Store & Product, showing Current Stock, Sell-through %, and Days of Supply. Apply conditional formatting (Red background if DoS < 5, Orange if < 15).
- **Table Grid**: Data Quality. Table Name, Ingested Rows, and Reconciliation status flag.
