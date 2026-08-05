select
    id as ticket_id,
    customer_id,
    issue_category,
    status,
    priority,
    ticket_timestamp,
    resolution_timestamp
from {{ source('silver', 'silver_support_tickets') }}
