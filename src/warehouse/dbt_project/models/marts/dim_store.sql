select
    md5(concat(store_id, '_1970-01-01')) as store_key,
    store_id,
    store_name,
    city,
    state,
    country,
    '1970-01-01 00:00:00'::timestamp as valid_from,
    '9999-12-31 23:59:59'::timestamp as valid_to,
    true as is_current
from {{ ref('stg_stores') }}
