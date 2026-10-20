select r.run_key
from {{ ref('fct_receipts') }} r
left join {{ ref('fct_line_items') }} i using (run_key)
group by r.run_key, r.subtotal, r.tax, r.total
having sum(i.amount) is distinct from r.subtotal
    or r.subtotal + r.tax is distinct from r.total
