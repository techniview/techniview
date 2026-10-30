.PHONY: install hooks fmt lint test check verify integration load-test performance-compare build up down clean

LOAD_STUDENTS ?= 100
LOAD_CONCURRENCY ?= $(LOAD_STUDENTS)
LOAD_COMPLETION_TIMEOUT_SECONDS ?= 1200
LOAD_APP_WORKERS ?= 4
GO_JUDGE_PARALLELISM ?= 4
DIRECT_WORKER_PROCESSES ?= 1
LOAD_CASES_PER_SUBMISSION ?= 1
PERF_BASE_PATH ?=
PERF_BASE_COMMIT ?= unknown
PERF_PROPOSED_COMMIT ?= HEAD
PERF_OUTPUT_DIR ?= /tmp/techniview-performance
PERF_STUDENTS ?= 100
PERF_APP_WORKERS ?= 4
PERF_WORKER_PROCESSES ?= 1
PERF_JUDGE_SLOTS ?= 4
PERF_RUNNER_CPU_LIMIT ?= 4
PERF_RUNNER_MEMORY_LIMIT ?= 8g
PERF_API_DB_POOL_SIZE ?= 30
PERF_WORKER_DB_POOL_SIZE ?= 3
PERF_DB_MAX_OVERFLOW ?= 0
PERF_GO_JUDGE_WALL_SECONDS ?= 30
PERF_WORKLOADS ?= short cpu-heavy multi-case
PERF_MEASURED_RUNS ?= 3

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
	@cleanup() { status=$$?; if [ $$status -ne 0 ]; then docker compose --env-file /dev/null -f compose.integration.yml logs --tail=100 backend app_worker || true; fi; docker compose --env-file /dev/null -f compose.integration.yml down --volumes --remove-orphans || true; exit $$status; }; \
	trap cleanup EXIT; \
	docker compose --env-file /dev/null -f compose.integration.yml up --build --attach tests --abort-on-container-exit --exit-code-from tests

load-test:
	@set -e; \
	cleanup() { status=$$?; if [ $$status -ne 0 ]; then docker compose --env-file /dev/null -f compose.integration.yml logs --tail=100 backend app_worker || true; fi; docker compose --env-file /dev/null -f compose.integration.yml down --volumes --remove-orphans || true; exit $$status; }; \
	trap cleanup EXIT; \
	GO_JUDGE_PARALLELISM=$(GO_JUDGE_PARALLELISM) DIRECT_WORKER_PROCESSES=$(DIRECT_WORKER_PROCESSES) docker compose --env-file /dev/null -f compose.integration.yml up -d --build --wait --scale app_worker=$(LOAD_APP_WORKERS) backend go-judge app_worker; \
	docker compose --env-file /dev/null -f compose.integration.yml build tests; \
	docker compose --env-file /dev/null -f compose.integration.yml run --rm --no-deps \
	  -e LOAD_STUDENTS=$(LOAD_STUDENTS) \
	  -e LOAD_CONCURRENCY=$(LOAD_CONCURRENCY) \
	  -e LOAD_CASES_PER_SUBMISSION=$(LOAD_CASES_PER_SUBMISSION) \
	  -e LOAD_APP_WORKERS=$(LOAD_APP_WORKERS) \
	  -e LOAD_GO_JUDGE_SLOTS=$(GO_JUDGE_PARALLELISM) \
	  -e LOAD_COMPLETION_TIMEOUT_SECONDS=$(LOAD_COMPLETION_TIMEOUT_SECONDS) \
	  tests python -m performance.load_test

performance-compare:
	@test -n "$(PERF_BASE_PATH)" || (echo "Set PERF_BASE_PATH to a base checkout" >&2; exit 2)
	PYTHONPATH=backend python3 scripts/performance/compare_load_test.py \
	  --base-path "$(PERF_BASE_PATH)" \
	  --base-commit "$(PERF_BASE_COMMIT)" \
	  --proposed-commit "$(PERF_PROPOSED_COMMIT)" \
	  --output-dir "$(PERF_OUTPUT_DIR)" \
	  --students "$(PERF_STUDENTS)" \
	  --app-workers "$(PERF_APP_WORKERS)" \
	  --worker-processes "$(PERF_WORKER_PROCESSES)" \
	  --judge-slots "$(PERF_JUDGE_SLOTS)" \
	  --runner-cpu-limit "$(PERF_RUNNER_CPU_LIMIT)" \
	  --runner-memory-limit "$(PERF_RUNNER_MEMORY_LIMIT)" \
	  --api-db-pool-size "$(PERF_API_DB_POOL_SIZE)" \
	  --worker-db-pool-size "$(PERF_WORKER_DB_POOL_SIZE)" \
	  --db-max-overflow "$(PERF_DB_MAX_OVERFLOW)" \
	  --go-judge-wall-seconds "$(PERF_GO_JUDGE_WALL_SECONDS)" \
	  --workloads $(PERF_WORKLOADS) \
	  --measured-runs "$(PERF_MEASURED_RUNS)"

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find backend -name "*.pyc" -delete 2>/dev/null; \
	echo "cleaned"

.DEFAULT_GOAL := install
