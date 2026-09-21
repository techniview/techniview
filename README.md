# TechniView 

<img src="https://github.com/techniview/.github/blob/main/TechniView%20Logo.png" width="150" height="150" style="border-radius: 50%;" alt="TechniView Logo">

LeetCode-style practice problems with class tracking attached. Built so interview prep connects back to coursework instead of living in a separate tab.

## Quick start

```
docker compose up -d --build
```

- Judge0 at http://localhost:2358
- Backend at http://localhost:8000/api/docs
- Frontend at http://localhost:5173
- Health check at http://localhost:8000/api/health

```
curl http://localhost:8000/api/health | jq
```

## What is in here

- docker-compose.yml - brings up Judge0, Postgres, Redis, MySQL and the backend
- backend - FastAPI on Python 3.14
  - main.py
  - requirements.txt
  - app/core - configuration, database, sessions, permissions, and API errors
  - app/routers - auth, courses, problems, assignments, analytics, and submissions
  - app/services - response shaping and shared analytics formulas
  - app/models - SQLAlchemy application schema
  - migrations - Alembic schema revisions
- frontend - Vite + React + strict TypeScript, currently just shows "techniview"
- docs - for the research writeup
- .githooks - versioned pre-commit hook
- pyproject.toml - ruff and pytest settings

## Config

Secrets live in `.env`, which is gitignored. Copy the template and change values:

```
cp .env.example .env
```

Compose works without `.env` too, it falls back to dev defaults.

## Dev setup

You need hooks for formatting and tests. They live in .githooks and are shared through git config. After you clone, hooks turn on the first time you run make or docker compose up. No extra install step if you follow quick start.

Run `make` to set up pre-commit hooks. Here's what each hook does:

- ruff check backend --fix - lint and fix imports and style
- ruff format backend - format to 88 columns, double quotes, Python 3.14
- pytest - runs cd backend && python -m pytest -q, must pass
- tsc --noEmit - strict typecheck for the frontend, no `any`, no unused vars
- eslint - strict TypeScript plus react-hooks rules for the frontend
- prettier --check - formatting for the frontend
- vitest - frontend unit tests, must pass

### Helpers

```
make fmt   # ruff fix + format, prettier --write
make lint  # ruff, tsc, eslint, prettier --check
make test  # pytest + vitest
make up    # docker compose up -d --build
make down  # docker compose down
```

When a hook fails, the commit is blocked and the hook prints only the fix commands for the checks that failed.

## Backend notes

Docker Compose applies the database migration and loads idempotent demo data before
starting the API. The local demo accounts are:

- `teacher@techniview.local` / `teacher-demo`
- `student@techniview.local` / `student-demo`

For a backend started outside Compose, run these commands from `backend/` first:

```
alembic upgrade head
python -m app.seed
```

The API uses an HTTP-only session cookie. Its OpenAPI contract is available at
`/api/docs`. Analytics use `difficulty`, `tag`, and, for course views,
`assignment_id` query filters.

Add a new endpoint by creating a file in backend/app/routers and including it in backend/main.py:

```
# create backend/app/routers/canvas.py
# then in main.py:
# app.include_router(canvas.router, prefix="/api")
```
