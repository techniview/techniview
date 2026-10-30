# TechniView

<img src="https://github.com/techniview/.github/blob/main/TechniView%20Logo.png" width="150" height="150" style="border-radius: 50%;" alt="TechniView Logo">

LeetCode-style practice problems with class tracking attached. Built so interview prep connects back to coursework instead of living in a separate tab.

## Quick start

```
docker compose up -d --build
```

- Runner API at http://localhost:2358 (Judge0-derived orchestration, go-judge execution)
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
  - app/worker - durable Judge0 dispatch, polling recovery, and email delivery
- frontend - Vite + React + strict TypeScript, with login, student problem/statistics, and teacher class/problem/analytics routes
- docs - research notes and tests; the design set is in [docs/design](docs/design/), with D0, D1, D2, user stories, and review notes
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
The fork builds separate API and Python worker images from a supported slim
base. Release CI publishes both to GHCR. Build and start them locally with
`docker compose up -d --build`; the worker needs Linux cgroup v2.
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
starting the API and application worker. The local demo accounts are:

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

Student submission requests return `202` with a submission ID. The application
worker dispatches cases to Judge0 and finalizes them through callbacks or polling.
`POST /api/problems/{id}/run` also returns `202` and uses the durable worker
pipeline for public cases. Run jobs do not consume a graded attempt. Execution
responses distinguish work waiting in TechniView from cases queued or running in
Judge0. The problem page offers separate Run and Submit actions; Submit uses all
server-owned cases. Both POST routes require an `Idempotency-Key`. The browser
reuses the key after a network failure and clears it after a successful response.
Keys expire after 24 hours. A new key starts a new run, even when the source code
is unchanged. The worker retries clear Judge0 `429` rejections with backoff. It
does not resend a request after an ambiguous network failure because Judge0 may
have accepted it. Repeated `429` responses finish with a retryable busy result;
the student can start a new run later. Keep `app_worker` running alongside the
API. Course enrollment, email verification,
and password recovery use an email outbox; local Compose captures messages in the
worker at `/tmp/techniview-mail`. For hosted delivery, set `EMAIL_DELIVERY_MODE=resend`,
`EMAIL_SIGNING_KEY`, `EMAIL_FROM`, `RESEND_API_KEY`, and `PUBLIC_APP_URL` on both API
and worker. The frontend handles join links, email verification, and password
recovery through its public account pages. See
[course and account setup](docs/course-accounts.md).

Course summaries update with grading transactions. Set a stable
`RESEARCH_EXPORT_SECRET` of at least 32 bytes before producing a research CSV.
See [backend reporting](docs/backend-reporting.md) for export fields and the
offline progress rebuild procedure. The [database recovery guide](docs/database-recovery.md)
has the Compose backup and restore steps.

`make integration` runs migrations against a fresh MySQL database, forces overlapping
callbacks under REPEATABLE READ, and runs Python submissions through Judge0. It
checks completion by reading MySQL without polling the submission API. The stack
uses separate containers, no host ports, and temporary database storage; it does
not read your `.env`. Judge0 uses the same privileged cgroup access as the dev
stack. Containers are removed when the command exits.

For a hosted installation, use [the campus deployment guide](docs/deployment.md).
Production uses separate application and runner VMs. The application Compose
stack serves HTTPS and keeps MySQL off host ports. The runner API binds only to
its private interface; its databases stay off host ports. Production imports the
reviewed catalog and does not create demo accounts. The current runner image must
be refreshed before it is used with real student submissions.

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
Trail progression is defined by the technique pools and their tiers. Individual
problems do not have prerequisites; students can open any published practice
problem even when another pool is currently recommended.

## Runner execution

The runner uses go-judge 1.13.3 with Python 3.14 and fresh sandbox/process state for every case. The existing Judge0-derived Rails API, PostgreSQL records, Redis queue and persistent Ruby workers own durable grouped jobs and callbacks. This is the measured hybrid architecture, not a standalone go-judge API replacement.

The worker build supports Linux amd64 and requires cgroup v2 with a private cgroup namespace. Its pinned binary checksum is checked during the image build. The execution endpoint listens only on loopback inside the worker container. Normal Compose files enable grouped dispatch and four application workers. Runner defaults are 16 execution workers, a 24 CPU quota and 8 GiB of memory. Set `JUDGE0_WORKER_COUNT`, `RUNNER_CPU_LIMIT` and `APP_WORKER_REPLICAS` for a smaller development machine. CPU quota is a ceiling, not an exclusive core reservation.

Application workers reuse HTTP connections. Group requests use stable identities and preserve individual case results. An interrupted execution with an uncertain outcome becomes an explicit infrastructure failure; recovery must not silently rerun it. Ruby workers recycle between completed groups; student Python processes never persist between cases.

For local Compose, the default group secret is development-only. Deployment Compose requires a `runner_group_secret` file in `SECRET_DIR`, containing at least 32 random characters. All application workers and the backend must use the same secret. Keep it stable while submissions are pending. Deployment Compose filenames retain their existing `production` names; no existing production installation is assumed.

See [runner decision and evidence](docs/runner-decision.md) for why this implementation was selected and its validation limits.
