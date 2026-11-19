select
    contract_id,
    installment_number,
    count(*) as duplicate_count
from {{ ref('silver_installments') }}
group by contract_id, installment_number
having count(*) > 1
