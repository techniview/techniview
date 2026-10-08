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
- internal-judge0-fork - Python-only Judge0 fork and maintenance notes
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
TechniView maintains an internal image derived from Judge0 in
`internal-judge0-fork/`, with Python 3.14 as its only active language.
This is a TechniView-owned fork, not an official Judge0 image, and it is not
published to a registry. Build and start it with `docker compose up -d --build`.
TechniView submissions do not include a language selector or Judge0 language
ID. The fork maps each request to its only active Python runtime internally;
Judge0 still uses a language database key for its own records.

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

### Professor authored content

Professors can create and copy problem drafts through `/api/problems`. Draft updates replace their ordered `test_cases` and `tags` collections. A draft needs a canonical Python solution that passes all cases before it can be published. Canonical solutions are stored for validation and are not returned by ordinary problem reads; hidden cases are likewise omitted from student-facing problem details. Published and archived problems are immutable; copy a problem to make a new editable draft.

Professors can also create private question sets at `/api/question-sets`, replace their ordered problem list with `PUT /api/question-sets/{id}/items`, and publish or archive the set. A set can include built-in published problems and the owner's custom problems. `POST /api/courses/{course_id}/assignments` creates a draft assignment from an owned published question set; the selected problem order is copied into assignment items. Publish it with `POST /api/courses/{course_id}/assignments/{assignment_id}/publish`.

### Built-in problem catalog

The built-in catalog combines APPS and APPS+ and removes duplicate statements.
The selected 500 problems include the 150-problem TechniView Trail and 350
additional practice problems. The raw datasets and curation scripts stay outside
this repository. The reviewed 500-problem import catalog is tracked at
`backend/data/problem_catalog.json`; it is loaded into MySQL and is not used as
the runtime store. Both dataset repositories identify their data as MIT licensed:
[APPS](https://github.com/hendrycks/apps/blob/main/LICENSE) and
[APPS+](https://github.com/Ablustrund/APPS_Plus/blob/main/LICENSE).

After applying migrations, import the reviewed catalog JSON with:

```
cd backend
uv run python -m scripts.import_problem_catalog data/problem_catalog.json
```

When this replaces the earlier APPS+ catalog, the importer archives its old
problems and the seeded demo problems, then removes them from the active
curriculum. Existing assignments can still refer to those archived rows.

The importer checks catalog size, source version, unique source IDs, typed tags,
test metadata, and public/hidden test visibility before writing. The October 7
selection audit rebuilt all 150 Trail entries around interview patterns and
independently calculated test answers. All 500 catalog reference solutions passed
8,371 stored cases through the backend execution wrapper on the local Python
runtime; 5,156 of those cases cover the Trail. This is a local execution check,
not a Judge0 deployment test. Trail reference syntax was also checked for Python
3.8 compatibility. Source data, test generators, and audit results live outside
the repository in `~/.local/share/techniview/trail-audit-20261007/`.

Linked-list inputs use arrays that the execution wrapper converts to `ListNode`
objects. Binary-tree inputs use breadth-first arrays with `null` for missing
children. Tree parameters are identified from the stored starter's `TreeNode`
annotations, so removing annotations from a submission does not change its input
contract. Returned trees are serialized in the same format. The platform supplies
both node classes. Each adapted problem describes its calling convention.

Technique tags group problems into the tiered TechniView Trail. Each pool
includes its tier, tier name, whether it is an extension, and any prerequisite
pools. Prerequisites guide recommendations but do not block access. A pool
recommends its next problem after the student passes one problem in every
prerequisite pool. Within each pool, problems are ordered easy to hard. Browse
the Trail at `GET /api/curriculum`; use `?kind=problem_type` for the secondary
classification view. The response includes problem IDs and summaries; fetch a
full statement and public examples with `GET /api/problems/{problem_id}`.
