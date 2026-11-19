{{
  config(
    unique_key=['contract_id', 'installment_number'],
    cluster_by=['status', 'contract_id'],
    contract={'enforced': true}
  )
}}

with source as (
    select *
    from {{ source('bronze', 'installments') }}
    {% if is_incremental() %}
        where
            updated_at
            >= timestamp_sub(current_timestamp(), interval {{ var('late_arrival_days') }} day)
    {% endif %}
),

ranked as (
    select
        contract_id,
        installment_number,
        due_date,
        paid_at,
        amount_due,
        amount_paid,
        updated_at,
        batch_id,
        source_file,
        ingested_at,
        ingestion_date,
        lower(trim(status)) as status,
        row_number() over (
            partition by contract_id, installment_number
            order by updated_at desc, ingested_at desc, source_file desc
        ) as record_rank
    from source
)

select
    contract_id,
    installment_number,
    due_date,
    paid_at,
    amount_due,
    amount_paid,
    status,
    updated_at,
    batch_id,
    source_file,
    ingested_at,
    ingestion_date
from ranked
where record_rank = 1
