select
    contract_id,
    start_date,
    end_date
from {{ ref('silver_contracts') }}
where end_date <= start_date
