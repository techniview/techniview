.PHONY: install hooks fmt lint test check verify integration load-test build up down clean

LOAD_STUDENTS ?= 100
LOAD_CONCURRENCY ?= $(LOAD_STUDENTS)
LOAD_COMPLETION_TIMEOUT_SECONDS ?= 1200
LOAD_APP_WORKERS ?= 4
LOAD_JUDGE0_WORKERS ?= 4
LOAD_CASES_PER_SUBMISSION ?= 1

install: hooks
	@uv sync --locked
	@cd frontend && npm ci --silent
	@echo "installed the locked uv environment + frontend dependencies"

hooks:
	git config core.hooksPath .githooks
	@echo "core.hooksPath = .githooks (hooks auto-run on git commit)"
	@echo "No pre-commit install needed, .githooks/pre-commit is versioned"

fmt:
	uv run ruff check backend --fix
	uv run ruff format backend
	cd frontend && npx prettier --write .

lint:
	uv run ruff check backend
	uv run ruff format --check backend
	cd frontend && npx tsc --noEmit
	cd frontend && npx eslint .
	cd frontend && npx prettier --check .

test:
	uv run python -m pytest -q
	cd frontend && npm test

check: lint test

build:
	cd frontend && npm run build

verify: check build integration

integration:
	@trap 'docker compose --env-file /dev/null -f compose.integration.yml down --volumes' EXIT; \
	docker compose --env-file /dev/null -f compose.integration.yml up --build --attach tests --abort-on-container-exit --exit-code-from tests

load-test:
	@set -e; \
	cleanup() { status=$$?; if [ $$status -ne 0 ]; then docker compose --env-file /dev/null -f compose.integration.yml logs --tail=100 backend app_worker || true; fi; docker compose --env-file /dev/null -f compose.integration.yml down --volumes || true; exit $$status; }; \
	trap cleanup EXIT; \
	LOAD_JUDGE0_WORKERS=$(LOAD_JUDGE0_WORKERS) docker compose --env-file /dev/null -f compose.integration.yml up -d --build --scale app_worker=$(LOAD_APP_WORKERS) backend judge workers app_worker; \
	docker compose --env-file /dev/null -f compose.integration.yml build tests; \
	docker compose --env-file /dev/null -f compose.integration.yml run --rm --no-deps \
	  -e LOAD_STUDENTS=$(LOAD_STUDENTS) \
	  -e LOAD_CONCURRENCY=$(LOAD_CONCURRENCY) \
	  -e LOAD_CASES_PER_SUBMISSION=$(LOAD_CASES_PER_SUBMISSION) \
	  -e LOAD_APP_WORKERS=$(LOAD_APP_WORKERS) \
	  -e LOAD_JUDGE0_WORKERS=$(LOAD_JUDGE0_WORKERS) \
	  -e LOAD_COMPLETION_TIMEOUT_SECONDS=$(LOAD_COMPLETION_TIMEOUT_SECONDS) \
	  tests python -m performance.load_test

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find backend -name "*.pyc" -delete 2>/dev/null; \
	echo "cleaned"

.DEFAULT_GOAL := install
