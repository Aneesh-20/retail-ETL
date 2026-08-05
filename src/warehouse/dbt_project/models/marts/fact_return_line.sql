select
    r.return_id,
    r.transaction_id,
    coalesce(p.product_key, md5('PRD-UNKNOWN')) as product_key,
    cast(r.return_timestamp as date) as date_day,
    r.quantity,
    r.refund_amount,
    r.return_reason,
    r.return_timestamp
from {{ ref('stg_returns') }} r
left join {{ ref('dim_product') }} p
    on r.product_id = p.product_id
    and r.return_timestamp >= p.valid_from
    and r.return_timestamp < p.valid_to
