# Noteguard make targets (B0). Python via uv (pinned 3.12, uv.lock); Node 22 for frontend/ (B3).
.PHONY: types setup test test-contracts test-engine test-api test-governance test-ui e2e run goldens fixtures openapi

setup:
	uv sync --frozen
	@if [ -f frontend/package-lock.json ]; then cd frontend && npm ci; fi

test:
	uv run pytest

test-contracts:
	uv run pytest -m contract

test-engine:
	uv run pytest -m engine

test-api:
	uv run pytest -m api

test-governance:
	uv run pytest -m governance

test-ui:
	@if [ -f frontend/package.json ]; then cd frontend && npm test; else uv run pytest -m ui; fi

e2e:
	uv run pytest -m e2e

run:
	uv run uvicorn noteguard.api.app:app --host 127.0.0.1 --port 8000

goldens:
	uv run python fixtures/expected/materialize.py

fixtures:
	uv run python fixtures/author_fixtures.py

openapi:
	uv run python scripts/export_openapi.py

types:
	uv run python scripts/export_openapi.py
	uv run python scripts/export_contract_data.py
	uv run python scripts/gen_ts_types.py
