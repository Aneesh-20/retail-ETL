select distinct
    md5(channel) as channel_key,
    channel as channel_name
from {{ ref('stg_transactions') }}
