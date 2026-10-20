select run_key, receipt_id, model, prompt_version, status,
       response->'receipt' as receipt, reasons,
       (response->>'cost_usd')::numeric as cost_usd,
       (response->>'latency_s')::numeric as latency_s
from {{ source('raw', 'extractions') }}
