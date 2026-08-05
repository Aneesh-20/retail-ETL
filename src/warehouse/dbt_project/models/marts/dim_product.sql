with product_ordered as (
    select
        product_id,
        sku,
        name,
        category,
        price,
        cost,
        updated_at,
        lead(updated_at) over (partition by product_id order by updated_at) as next_updated_at
    from {{ ref('stg_products') }}
)
select
    md5(concat(product_id, '_', coalesce(cast(updated_at as varchar), '1970-01-01'))) as product_key,
    product_id,
    sku,
    name,
    category,
    price,
    cost,
    updated_at as valid_from,
    coalesce(next_updated_at - interval '1 second', '9999-12-31 23:59:59'::timestamp) as valid_to,
    case when next_updated_at is null then true else false end as is_current
from product_ordered
