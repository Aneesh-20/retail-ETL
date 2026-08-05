select
    t.transaction_line_id,
    t.transaction_id,
    coalesce(c.customer_key, md5('CUST-UNKNOWN')) as customer_key,
    coalesce(p.product_key, md5('PRD-UNKNOWN')) as product_key,
    coalesce(s.store_key, md5('ST-UNKNOWN')) as store_key,
    md5(t.channel) as channel_key,
    md5(
        case 
            when t.discount = 0 then 'PROMO-NONE'
            when t.discount <= 5.0 then 'PROMO-SEASONAL'
            when t.discount <= 15.0 then 'PROMO-LOYALTY'
            else 'PROMO-FLASH'
        end
    ) as promotion_key,
    cast(t.transaction_timestamp as date) as date_day,
    t.quantity,
    t.unit_price,
    t.discount,
    (t.quantity * t.unit_price) - t.discount as net_sales,
    (t.quantity * coalesce(p.cost, 0.0)) as total_cost,
    ((t.quantity * t.unit_price) - t.discount) - (t.quantity * coalesce(p.cost, 0.0)) as gross_margin,
    t.transaction_timestamp
from {{ ref('stg_transactions') }} t
-- Event-time resolution for customer (SCD Type 2)
left join {{ ref('dim_customer') }} c
    on t.customer_id = c.customer_id
    and t.transaction_timestamp >= c.valid_from
    and t.transaction_timestamp < c.valid_to
-- Event-time resolution for product (SCD Type 2)
left join {{ ref('dim_product') }} p
    on t.product_id = p.product_id
    and t.transaction_timestamp >= p.valid_from
    and t.transaction_timestamp < p.valid_to
-- Event-time resolution for store
left join {{ ref('dim_store') }} s
    on t.store_id = s.store_id
    and t.transaction_timestamp >= s.valid_from
    and t.transaction_timestamp < s.valid_to
