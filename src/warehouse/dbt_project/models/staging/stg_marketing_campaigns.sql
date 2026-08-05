select
    id as campaign_id,
    campaign_name,
    channel,
    cast(cost as decimal(18,2)) as cost,
    cast(impressions as integer) as impressions,
    cast(clicks as integer) as clicks,
    cast(conversions as integer) as conversions,
    campaign_date
from {{ source('silver', 'silver_marketing_campaigns') }}
