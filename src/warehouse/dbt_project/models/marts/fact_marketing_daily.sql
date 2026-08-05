select
    m.campaign_id,
    coalesce(c.campaign_key, md5('CAMP-UNKNOWN')) as campaign_key,
    cast(m.campaign_date as date) as date_day,
    m.cost,
    m.impressions,
    m.clicks,
    m.conversions,
    case when m.clicks > 0 then cast(m.conversions as decimal(18,4)) / m.clicks else 0.0 end as click_to_conv_rate
from {{ ref('stg_marketing_campaigns') }} m
left join {{ ref('dim_campaign') }} c
    on m.campaign_id = c.campaign_id
    and cast(m.campaign_date as date) >= c.valid_from
    and cast(m.campaign_date as date) < c.valid_to
