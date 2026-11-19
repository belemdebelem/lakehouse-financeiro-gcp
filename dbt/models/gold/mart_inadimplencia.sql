with installments as (
    select *
    from {{ ref('silver_installments') }}
),

contracts as (
    select
        contract_id,
        product_type
    from {{ ref('silver_contracts') }}
),

params as (
    select date '{{ var("as_of_date") }}' as as_of_date
)

select
    date_trunc(i.due_date, month) as due_month,
    c.product_type,
    count(*) as overdue_installment_count,
    sum(
        i.amount_due - case
            when i.paid_at is not null and i.paid_at <= p.as_of_date then i.amount_paid
            else 0
        end
    ) as overdue_amount,
    max(date_diff(p.as_of_date, i.due_date, day)) as max_overdue_days
from installments as i
join contracts as c
    on i.contract_id = c.contract_id
cross join params as p
where i.due_date < p.as_of_date
    and (i.paid_at is null or i.paid_at > p.as_of_date)
    and i.status in ('open', 'overdue')
group by date_trunc(i.due_date, month), c.product_type
