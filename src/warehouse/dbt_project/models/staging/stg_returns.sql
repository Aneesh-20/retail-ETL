select
    id as return_id,
    transaction_id,
    product_id,
    cast(quantity as integer) as quantity,
    cast(refund_amount as decimal(18,2)) as refund_amount,
    return_reason,
    return_timestamp
from {{ source('silver', 'silver_returns') }}
