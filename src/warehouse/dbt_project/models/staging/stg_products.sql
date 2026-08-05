select
    id as product_id,
    sku,
    name,
    category,
    cast(price as decimal(18,2)) as price,
    cast(cost as decimal(18,2)) as cost,
    event_timestamp as updated_at
from {{ source('silver', 'silver_products') }}
