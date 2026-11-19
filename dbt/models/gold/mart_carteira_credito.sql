with contracts as (
    select *
    from {{ ref('silver_contracts') }}
),

bounds as (
    select
        date_trunc(min(start_date), month) as min_month,
        date_trunc(date '{{ var("as_of_date") }}', month) as max_month
    from contracts
),

months as (
    select month_start
    from bounds
    cross join unnest(
        generate_date_array(bounds.min_month, bounds.max_month, interval 1 month)
    ) as month_start
),

month_ends as (
    select
        month_start,
        last_day(month_start, month) as month_end
    from months
)

select
    m.month_start as reference_month,
    c.product_type,
    sum(c.principal_amount) as original_principal_amount,
    count(*) as contract_count
from month_ends as m
join contracts as c
    on c.start_date <= m.month_end
    and c.end_date >= m.month_end
    and c.status in ('active', 'closed')
group by m.month_start, c.product_type
