select receipt_id, sha256, source_revision, labels
from {{ source('raw', 'receipts') }}
