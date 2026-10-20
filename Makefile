.PHONY: setup up download demo check dbt dagster
setup:
	uv sync --frozen
up:
	docker compose up -d --wait
download:
	uv run receipts download
demo:
	uv run receipts demo
check:
	uv run ruff check .
	uv run pytest
dbt:
	uv run receipts dbt
dagster:
	uv run dagster dev -m receipt_pipeline.assets
