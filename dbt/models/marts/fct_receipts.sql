select a.run_key, a.receipt_id, a.model, a.prompt_version, a.label_id,
       a.receipt->'merchant'->>'value' as merchant,
       (a.receipt->'date'->>'value')::date as receipt_date,
       (a.receipt->'subtotal'->>'value')::numeric as subtotal,
       (a.receipt->'tax'->>'value')::numeric as tax,
       (a.receipt->'total'->>'value')::numeric as total,
       a.cost_usd, a.latency_s, r.source_revision
from {{ ref('int_accepted') }} a
join {{ ref('stg_receipts') }} r using (receipt_id)
