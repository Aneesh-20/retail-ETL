select
    id as transaction_line_id,
    transaction_id,
    customer_id,
    store_id,
    channel,
    product_id,
    cast(quantity as integer) as quantity,
    cast(unit_price as decimal(18,2)) as unit_price,
    cast(discount as decimal(18,2)) as discount,
    transaction_timestamp
from {{ source('silver', 'silver_transactions') }}
