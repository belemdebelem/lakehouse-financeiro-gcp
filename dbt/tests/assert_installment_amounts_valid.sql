select
    contract_id,
    installment_number,
    amount_due,
    amount_paid
from {{ ref('silver_installments') }}
where amount_due <= 0
    or amount_paid < 0
    or amount_paid > amount_due
