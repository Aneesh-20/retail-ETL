select
    m.movement_id,
    coalesce(p.product_key, md5('PRD-UNKNOWN')) as product_key,
    coalesce(s.store_key, md5('ST-UNKNOWN')) as store_key,
    m.movement_type,
    m.quantity,
    cast(m.movement_timestamp as date) as date_day,
    m.movement_timestamp
from {{ ref('stg_inventory_movements') }} m
left join {{ ref('dim_product') }} p
    on m.product_id = p.product_id
    and m.movement_timestamp >= p.valid_from
    and m.movement_timestamp < p.valid_to
left join {{ ref('dim_store') }} s
    on m.store_id = s.store_id
    and m.movement_timestamp >= s.valid_from
    and m.movement_timestamp < s.valid_to
