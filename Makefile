.PHONY: install hooks fmt lint test up down clean

install: hooks
	@pip install -q pre-commit ruff 2>&1 | tail -3 || pip install --break-system-packages -q pre-commit ruff 2>&1 | tail -3
	@pip install -q -r backend/requirements.txt pytest 2>&1 | tail -3 || pip install --break-system-packages -q -r backend/requirements.txt pytest 2>&1 | tail -3
	@cd frontend && npm install --silent 2>&1 | tail -3
	@echo "installed pre-commit + ruff + backend deps + frontend deps"

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

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find backend -name "*.pyc" -delete 2>/dev/null; \
	echo "cleaned"

.DEFAULT_GOAL := install
