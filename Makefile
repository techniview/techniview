.PHONY: install hooks fmt lint test check verify integration build up down clean

install: hooks
	@python -m pip install -q pre-commit ruff pip-audit pytest pytest-cov || python -m pip install --break-system-packages -q pre-commit ruff pip-audit pytest pytest-cov
	@python -m pip install -q -r backend/requirements.txt || python -m pip install --break-system-packages -q -r backend/requirements.txt
	@cd frontend && npm ci --silent
	@echo "installed pre-commit + Python tools + backend deps + frontend deps"

hooks:
	git config core.hooksPath .githooks
	@echo "core.hooksPath = .githooks (hooks auto-run on git commit)"
	@echo "No pre-commit install needed, .githooks/pre-commit is versioned"

fmt:
	ruff check backend --fix
	ruff format backend
	cd frontend && npx prettier --write .

lint:
	ruff check backend
	ruff format --check backend
	cd frontend && npx tsc --noEmit
	cd frontend && npx eslint .
	cd frontend && npx prettier --check .

test:
	cd backend && python -m pytest -q
	cd frontend && npm test

check: lint test

build:
	cd frontend && npm run build

verify: check build integration

integration:
	@trap 'docker compose --env-file /dev/null -f compose.integration.yml down --volumes' EXIT; \
	docker compose --env-file /dev/null -f compose.integration.yml up --build --attach tests --abort-on-container-exit --exit-code-from tests

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find backend -name "*.pyc" -delete 2>/dev/null; \
	echo "cleaned"

.DEFAULT_GOAL := install
