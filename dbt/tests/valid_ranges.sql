select run_key from {{ ref('fct_receipts') }}
where subtotal < 0 or tax < 0 or total < 0 or cost_usd < 0 or latency_s < 0
union all
select run_key from {{ ref('fct_line_items') }} where amount < 0 or quantity <= 0
