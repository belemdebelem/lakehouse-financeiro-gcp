select
    reference_month,
    product_type,
    count(*) as duplicate_count
from {{ ref('mart_carteira_credito') }}
group by reference_month, product_type
having count(*) > 1
