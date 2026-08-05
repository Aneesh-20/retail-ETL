select
    id as customer_id,
    first_name,
    last_name,
    email,
    phone,
    gender,
    state,
    birth_date,
    event_timestamp as updated_at
from {{ source('silver', 'silver_customers') }}
