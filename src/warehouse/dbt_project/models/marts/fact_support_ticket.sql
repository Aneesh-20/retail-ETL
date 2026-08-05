select
    s.ticket_id,
    coalesce(c.customer_key, md5('CUST-UNKNOWN')) as customer_key,
    cast(s.ticket_timestamp as date) as date_day,
    s.issue_category,
    s.status,
    s.priority,
    s.ticket_timestamp,
    s.resolution_timestamp,
    case 
        when s.resolution_timestamp is not null 
        then extract(epoch from (s.resolution_timestamp - s.ticket_timestamp)) / 3600.0 
        else null 
    end as resolution_time_hours
from {{ ref('stg_support_tickets') }} s
left join {{ ref('dim_customer') }} c
    on s.customer_id = c.customer_id
    and s.ticket_timestamp >= c.valid_from
    and s.ticket_timestamp < c.valid_to
