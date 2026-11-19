select
    due_month,
    product_type,
    count(*) as duplicate_count
from {{ ref('mart_inadimplencia') }}
group by due_month, product_type
having count(*) > 1
