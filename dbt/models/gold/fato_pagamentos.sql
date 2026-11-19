with installments as (
    select *
    from {{ ref('silver_installments') }}
    where paid_at is not null
),

contracts as (
    select
        contract_id,
        customer_id,
        product_type
    from {{ ref('silver_contracts') }}
)

select
    i.contract_id,
    i.installment_number,
    c.customer_id,
    c.product_type,
    i.paid_at as payment_date,
    i.due_date,
    i.amount_paid,
    i.amount_due,
    date_trunc(i.paid_at, month) as payment_month,
    date_diff(i.due_date, i.paid_at, day) as days_until_due_at_payment
from installments as i
inner join contracts as c
    on i.contract_id = c.contract_id
