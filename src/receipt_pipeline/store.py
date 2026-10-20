import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb

from receipt_pipeline.schema import Receipt, validate

DDL = """
create schema if not exists raw;
create table if not exists raw.receipts (
 receipt_id text primary key, image_path text not null, sha256 text not null,
 source_revision text not null, labels jsonb not null
);
create table if not exists raw.extractions (
 run_key text primary key, receipt_id text not null references raw.receipts,
 model text not null, prompt_version text not null, response jsonb not null,
 reasons jsonb not null default '[]', status text not null default 'pending'
);
create table if not exists raw.review_queue (
 run_key text primary key references raw.extractions,
 reasons jsonb not null, status text not null default 'pending'
);
create table if not exists raw.corrections (
 label_id bigint generated always as identity primary key,
 run_key text not null references raw.extractions,
 receipt_id text not null references raw.receipts,
 label jsonb not null, reviewer text not null, action text not null,
 created_at timestamptz not null default now()
);
"""


@contextmanager
def connect():
    config = dotenv_values(".env")
    dsn = os.getenv("DATABASE_URL") or config.get("DATABASE_URL")
    dsn = dsn or "postgresql://receipts:receipts@localhost:5432/receipts"
    with psycopg.connect(dsn) as conn:
        yield conn


def initialize(conn):
    conn.execute(DDL)


def ingest(conn, manifest):
    initialize(conn)
    for row in manifest["receipts"]:
        conn.execute(
            "insert into raw.receipts values (%s,%s,%s,%s,%s) "
            "on conflict (receipt_id) do update set image_path=excluded.image_path, "
            "sha256=excluded.sha256, source_revision=excluded.source_revision, "
            "labels=excluded.labels",
            (row["id"], row["image"], row["sha256"], manifest["revision"], Jsonb(row["labels"])),
        )


def save_extraction(conn, receipt_id, response):
    conn.execute(
        "insert into raw.extractions (run_key,receipt_id,model,prompt_version,response) "
        "values (%s,%s,%s,%s,%s) on conflict (run_key) do nothing",
        (
            response["key"],
            receipt_id,
            response["model"],
            response["prompt_version"],
            Jsonb(response),
        ),
    )


def validate_all(conn):
    for key, response in conn.execute("select run_key,response from raw.extractions"):
        try:
            reasons = (
                [response["error"]]
                if response.get("error")
                else validate(Receipt.model_validate(response["receipt"]))
            )
        except ValueError:
            reasons = ["invalid_response"]
        status = "rejected" if reasons else "accepted"
        conn.execute(
            "update raw.extractions set reasons=%s,status=%s where run_key=%s",
            (Jsonb(reasons), status, key),
        )
        if reasons:
            conn.execute(
                "insert into raw.review_queue (run_key,reasons) values (%s,%s) "
                "on conflict (run_key) do update set reasons=excluded.reasons",
                (key, Jsonb(reasons)),
            )


def review(conn, key, reviewer, corrected: Receipt | None = None):
    """Append immutable labels; never overwrite source labels or model outputs."""
    row = conn.execute(
        "select e.receipt_id,e.response,q.status from raw.extractions e "
        "join raw.review_queue q using(run_key) where run_key=%s for update of q",
        (key,),
    ).fetchone()
    if row is None or row[2] != "pending":
        raise ValueError("No pending review for this run")
    receipt = corrected or Receipt.model_validate(row[1]["receipt"])
    reasons = validate(receipt, threshold=0)
    # Human may accept low model confidence, but cannot bypass arithmetic/missing evidence.
    if reasons:
        raise ValueError("Correction fails validation: " + ",".join(reasons))
    if not reviewer.strip():
        raise ValueError("Reviewer identity required")
    conn.execute(
        "insert into raw.corrections (run_key,receipt_id,label,reviewer,action) "
        "values (%s,%s,%s,%s,%s)",
        (
            key,
            row[0],
            Jsonb(receipt.model_dump(mode="json")),
            reviewer,
            "correct" if corrected else "accept",
        ),
    )
    conn.execute("update raw.review_queue set status='resolved' where run_key=%s", (key,))


def export_labels(conn, path: Path):
    rows = conn.execute(
        "select label_id,receipt_id,label,reviewer,created_at::text "
        "from raw.corrections order by label_id"
    ).fetchall()
    path.write_text(
        json.dumps(
            [
                dict(
                    zip(
                        ["label_id", "receipt_id", "label", "reviewer", "created_at"],
                        row,
                        strict=True,
                    )
                )
                for row in rows
            ],
            indent=2,
        )
    )
