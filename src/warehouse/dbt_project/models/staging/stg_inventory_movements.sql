select
    id as movement_id,
    product_id,
    store_id,
    movement_type,
    cast(quantity as integer) as quantity,
    movement_timestamp
from {{ source('silver', 'silver_inventory_movements') }}
