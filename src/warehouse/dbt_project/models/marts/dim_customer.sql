with customer_ordered as (
    select
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        gender,
        state,
        birth_date,
        updated_at,
        lead(updated_at) over (partition by customer_id order by updated_at) as next_updated_at
    from {{ ref('stg_customers') }}
)
select
    md5(concat(customer_id, '_', coalesce(cast(updated_at as varchar), '1970-01-01'))) as customer_key,
    customer_id,
    first_name,
    last_name,
    email,
    phone,
    gender,
    state,
    birth_date,
    updated_at as valid_from,
    coalesce(next_updated_at - interval '1 second', '9999-12-31 23:59:59'::timestamp) as valid_to,
    case when next_updated_at is null then true else false end as is_current
from customer_ordered
