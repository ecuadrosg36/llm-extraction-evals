select a.run_key || ':' || item.ordinality::text as line_id,
       a.run_key, item.ordinality as line_number,
       item.value->'name'->>'value' as name,
       (item.value->'quantity'->>'value')::numeric as quantity,
       (item.value->'amount'->>'value')::numeric as amount
from {{ ref('int_accepted') }} a,
lateral jsonb_array_elements(a.receipt->'line_items') with ordinality as item(value, ordinality)
