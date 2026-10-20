with latest_labels as (
    select distinct on (run_key) run_key, label, label_id
    from {{ source('raw', 'corrections') }}
    order by run_key, label_id desc
)
select e.run_key, e.receipt_id, e.model, e.prompt_version,
       coalesce(c.label, e.receipt) as receipt,
       c.label_id, e.cost_usd, e.latency_s
from {{ ref('stg_extractions') }} e
left join latest_labels c using (run_key)
where e.status = 'accepted' or c.label_id is not null
