with unioned_activities as (
    -- Transactions
    select
        customer_id,
        transaction_timestamp as activity_timestamp,
        'PURCHASE' as activity_type,
        'Completed a transaction: ' || transaction_id as activity_details
    from {{ ref('stg_transactions') }}
    where customer_id is not null
    
    union all
    
    -- Returns
    select
        t.customer_id,
        r.return_timestamp as activity_timestamp,
        'RETURN' as activity_type,
        'Returned product in transaction: ' || r.transaction_id as activity_details
    from {{ ref('stg_returns') }} r
    join {{ ref('stg_transactions') }} t on r.transaction_id = t.transaction_id
    where t.customer_id is not null
    
    union all
    
    -- Support Tickets
    select
        customer_id,
        ticket_timestamp as activity_timestamp,
        'SUPPORT' as activity_type,
        'Opened support ticket: ' || ticket_id || ' - ' || issue_category as activity_details
    from {{ ref('stg_support_tickets') }}
    where customer_id is not null
)
select
    md5(concat(customer_id, '_', cast(activity_timestamp as varchar), '_', activity_type)) as activity_key,
    coalesce(c.customer_key, md5('CUST-UNKNOWN')) as customer_key,
    activity_timestamp,
    cast(activity_timestamp as date) as date_day,
    activity_type,
    activity_details
from unioned_activities u
left join {{ ref('dim_customer') }} c
    on u.customer_id = c.customer_id
    and u.activity_timestamp >= c.valid_from
    and u.activity_timestamp < c.valid_to
