{{
  config(
    unique_key=['contract_id'],
    cluster_by=['product_type', 'status'],
    contract={'enforced': true}
  )
}}

with source as (
    select *
    from {{ source('bronze', 'contracts') }}
    {% if is_incremental() %}
    where updated_at >= timestamp_sub(current_timestamp(), interval {{ var('late_arrival_days') }} day)
    {% endif %}
),

ranked as (
    select
        contract_id,
        customer_id,
        lower(trim(product_type)) as product_type,
        principal_amount,
        annual_interest_rate,
        start_date,
        end_date,
        lower(trim(status)) as status,
        updated_at,
        batch_id,
        source_file,
        ingested_at,
        ingestion_date,
        row_number() over (
            partition by contract_id
            order by updated_at desc, ingested_at desc, source_file desc
        ) as record_rank
    from source
)

select
    contract_id,
    customer_id,
    product_type,
    principal_amount,
    annual_interest_rate,
    start_date,
    end_date,
    status,
    updated_at,
    batch_id,
    source_file,
    ingested_at,
    ingestion_date
from ranked
where record_rank = 1
