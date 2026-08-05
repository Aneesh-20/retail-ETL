with campaign_ordered as (
    select distinct
        campaign_id,
        campaign_name,
        channel,
        campaign_date,
        lead(campaign_date) over (partition by campaign_id order by campaign_date) as next_campaign_date
    from {{ ref('stg_marketing_campaigns') }}
)
select
    md5(concat(campaign_id, '_', coalesce(campaign_date, '1970-01-01'))) as campaign_key,
    campaign_id,
    campaign_name,
    channel,
    cast(campaign_date as date) as valid_from,
    cast(coalesce(next_campaign_date, '9999-12-31') as date) as valid_to,
    case when next_campaign_date is null then true else false end as is_current
from campaign_ordered
