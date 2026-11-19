select
    i.contract_id,
    i.installment_number,
    i.paid_at,
    c.start_date
from {{ ref('silver_installments') }} as i
join {{ ref('silver_contracts') }} as c
    on i.contract_id = c.contract_id
where i.paid_at is not null
    and i.paid_at < c.start_date
