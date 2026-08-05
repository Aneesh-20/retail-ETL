# Privacy and PII Governance Policy

This document establishes the security, compliance, and privacy controls implemented across the Enterprise Retail Lakehouse Platform to safeguard customer Personal Identifiable Information (PII).

---

## 1. PII Classification Registry

We classify database columns containing sensitive personal attributes into the following tiers:

| Table | Column | Sensitive Type | Encryption / Obfuscation Strategy |
|---|---|---|---|
| `silver_customers` | `first_name` | Direct PII | Masked (e.g. `J****`) / Role-Based Access Control |
| `silver_customers` | `last_name` | Direct PII | Masked (e.g. `S****`) / Role-Based Access Control |
| `silver_customers` | `email` | Direct PII | Tokenized / Obfuscated (e.g. `j***@***.com`) |
| `silver_customers` | `phone` | Direct PII | Masked (e.g. `+1-***-***-0123`) |
| `silver_customers` | `birth_date` | Indirect PII | Rounded to Year-Month (e.g. `1985-05-01`) for Age Analytics |

---

## 2. Ingestion & Storage Rules

1. **Bronze Immutability**:
   - Raw JSON payloads inside Bronze Delta tables contain active PII.
   - Access to Bronze directories is restricted strictly to ETL pipelines.
   - Direct querying of Bronze tables by analysts or BI dashboards is strictly prohibited.
2. **Silver Masking**:
   - During the Silver cleaning phase, any email pattern checks are run, and strings are trimmed.
   - In production environments, raw PII fields can be dynamically masked or tokenized before writing to silver Delta tables.
3. **Gold Serving**:
   - Access to the Gold Warehouse layer (`retail_warehouse` PostgreSQL) is regulated using database views.
   - A `v_dim_customer` view can be created to redact or mask names, email addresses, and phone numbers for non-security users.

---

## 3. Masking Implementation Example

The following standard SQL view demonstrates the customer dimension masking rule deployed in Gold:

```sql
CREATE VIEW v_dim_customer AS
SELECT
    customer_key,
    customer_id,
    -- Mask first name
    overlay(first_name placing '***' from 2) as first_name_masked,
    -- Mask last name
    overlay(last_name placing '***' from 2) as last_name_masked,
    -- Mask email: keep first char and domain
    split_part(email, '@', 1) as email_user,
    overlay(split_part(email, '@', 1) placing '***' from 2) || '@' || split_part(email, '@', 2) as email_masked,
    -- Mask phone
    '***-***-' || right(phone, 4) as phone_masked,
    gender,
    state,
    birth_date,
    valid_from,
    valid_to,
    is_current
FROM dim_customer;
```

---

## 4. Operational GDPR Compliance (Right to be Forgotten)

Under GDPR / CCPA, customers have the right to request deletion of their records. The platform handles deletions as follows:

1. **Soft Deletions**: Anonymize the PII fields (e.g. update names to `DELETED_USER`, emails to `forgotten@compliance.com`, phone numbers to empty) inside the Gold `dim_customer` and Silver `silver_customers` tables.
2. **Fact Retention**: Keep all metrics inside transactional facts (`fact_sales_line`, `fact_return_line`) unchanged. The facts reference the `customer_key` or `customer_id` which now resolves to a masked `DELETED_USER` profile. This preserves financial ledger aggregates while removing all individual identity identifiers.
