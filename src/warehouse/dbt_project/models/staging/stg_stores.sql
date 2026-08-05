select
    id as store_id,
    name as store_name,
    city,
    state,
    country
from {{ source('silver', 'silver_stores') }}
