with promo_cte as (
    select distinct
        case 
            when discount = 0 then 'PROMO-NONE'
            when discount <= 5.0 then 'PROMO-SEASONAL'
            when discount <= 15.0 then 'PROMO-LOYALTY'
            else 'PROMO-FLASH'
        end as promotion_id,
        case 
            when discount = 0 then 'No Promotion'
            when discount <= 5.0 then 'Seasonal Sale (Up to $5)'
            when discount <= 15.0 then 'Loyalty Rewards Tier'
            else 'Flash Sale Special'
        end as promotion_name,
        case
            when discount = 0 then 0.0
            when discount <= 5.0 then 0.10
            when discount <= 15.0 then 0.20
            else 0.35
        end as discount_rate
    from {{ ref('stg_transactions') }}
)
select
    md5(promotion_id) as promotion_key,
    promotion_id,
    promotion_name,
    discount_rate
from promo_cte
