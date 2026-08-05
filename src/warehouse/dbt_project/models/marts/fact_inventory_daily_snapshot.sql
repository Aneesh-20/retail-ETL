with dates as (
    select date_day from {{ ref('dim_date') }}
),
prod_store as (
    select distinct product_key, store_key from {{ ref('fact_inventory_movement') }}
),
calendar_grid as (
    select d.date_day, ps.product_key, ps.store_key
    from dates d
    cross join prod_store ps
),
daily_movements as (
    select
        date_day,
        product_key,
        store_key,
        sum(quantity) as net_movement
    from {{ ref('fact_inventory_movement') }}
    group by 1, 2, 3
),
cumulative_movements as (
    select
        cg.date_day,
        cg.product_key,
        cg.store_key,
        coalesce(dm.net_movement, 0) as daily_net,
        sum(coalesce(dm.net_movement, 0)) over (
            partition by cg.product_key, cg.store_key 
            order by cg.date_day
            rows between unbounded preceding and current row
        ) as stock_on_hand
    from calendar_grid cg
    left join daily_movements dm
        on cg.date_day = dm.date_day
        and cg.product_key = dm.product_key
        and cg.store_key = dm.store_key
)
select
    md5(concat(cast(date_day as varchar), '_', product_key, '_', store_key)) as snapshot_key,
    date_day,
    product_key,
    store_key,
    stock_on_hand
from cumulative_movements
where date_day <= current_date
