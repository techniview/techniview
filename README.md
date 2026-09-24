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
- pyproject.toml - backend dependencies and Ruff/pytest settings
- uv.lock - reproducible Python dependency lockfile

## Config

Secrets live in `.env`, which is gitignored. Copy the template and change values:

```
cp .env.example .env
```

Compose works without `.env` too, it falls back to dev defaults.

Judge0 sends completed execution reports to the backend callback URL. Compose
uses `http://backend:8000/api/internal/judge0/callbacks` by default. Set
`JUDGE0_CALLBACK_BASE_URL` when Judge0 needs a different route to reach the API.

## Dev setup

You need hooks for formatting and tests. They live in `.githooks` and are shared
through Git config. Install [uv](https://docs.astral.sh/uv/), then run `make install`
after cloning. It creates the locked Python environment, installs frontend
dependencies, and turns the hooks on. Hooks run checks only. They do not install
tools or rewrite files.

`make check` runs the local checks. `make verify` also builds the frontend and
runs the temporary MySQL/Judge0 integration suite. The checks are:

- ruff check backend - lint imports and style
- ruff format --check backend - verify 88-column, double-quote formatting
- pytest - runs the backend test suite
- tsc --noEmit - strict typecheck for the frontend, no `any`, no unused vars
- eslint - strict TypeScript plus react-hooks rules for the frontend
- prettier --check - formatting for the frontend
- vitest - frontend unit tests, must pass

### Helpers

```
make fmt   # ruff fix + format, prettier --write
make check # lint and fast tests
make build # frontend production build
make verify # check + build + integration tests
make integration # disposable MySQL + Judge0 integration stack (requires Docker)
make up    # docker compose up -d --build
make down  # docker compose down
```

Read [docs/testing.md](docs/testing.md) for the full contributor workflow, test
boundaries, CI jobs, and failure reproduction commands.

When a hook fails, the commit is blocked and the failing command's output is shown;
run the matching `make` command above to fix or reproduce it.

## Backend notes

Docker Compose applies the database migration and loads idempotent demo data before
starting the API. The local demo accounts are:

- `teacher@techniview.local` / `teacher-demo`
- `student@techniview.local` / `student-demo`

For a backend started outside Compose, run these commands from the repository root:

```
uv run alembic upgrade head
uv run python -m app.seed
```

The API uses an HTTP-only session cookie. Its OpenAPI contract is available at
`/api/docs`. Analytics use `difficulty`, `tag`, and, for course views,
`assignment_id` query filters.

`make integration` runs migrations against a fresh MySQL database, forces overlapping
callbacks under REPEATABLE READ, and runs Python submissions through Judge0. It
checks completion by reading MySQL without polling the submission API. The stack
uses separate containers, no host ports, and temporary database storage; it does
not read your `.env`. Judge0 uses the same privileged cgroup access as the dev
stack. Containers are removed when the command exits.

Add a new endpoint by creating a file in backend/app/routers and including it in backend/main.py:

```
# create backend/app/routers/canvas.py
# then in main.py:
# app.include_router(canvas.router, prefix="/api")
```
