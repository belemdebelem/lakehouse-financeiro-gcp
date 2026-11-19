{{
  config(
    unique_key=['customer_id'],
    cluster_by=['customer_segment'],
    contract={'enforced': true}
  )
}}

with source as (
    select *
    from {{ source('bronze', 'customers') }}
    {% if is_incremental() %}
        where
            updated_at
            >= timestamp_sub(current_timestamp(), interval {{ var('late_arrival_days') }} day)
    {% endif %}
),

ranked as (
    select
        customer_id,
        created_at,
        updated_at,
        batch_id,
        source_file,
        ingested_at,
        ingestion_date,
        lower(trim(customer_segment)) as customer_segment,
        row_number() over (
            partition by customer_id
            order by updated_at desc, ingested_at desc, source_file desc
        ) as record_rank
    from source
)

select
    customer_id,
    customer_segment,
    created_at,
    updated_at,
    batch_id,
    source_file,
    ingested_at,
    ingestion_date
from ranked
where record_rank = 1
