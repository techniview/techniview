# TechniView

<img src="https://github.com/techniview/.github/blob/main/TechniView%20Logo.png" width="150" height="150" style="border-radius: 50%;" alt="TechniView Logo">

LeetCode-style practice problems with class tracking attached. Built so interview prep connects back to coursework instead of living in a separate tab.

## Quick start

```
docker compose up -d --build
```

- go-judge sandbox at http://localhost:5050 (private in production)
- Backend at http://localhost:8000/api/docs
- Frontend at http://localhost:5173
- Health check at http://localhost:8000/api/health

```
curl http://localhost:8000/api/health | jq
```

## What is in here

- docker-compose.yml - brings up go-judge, MySQL, the backend, and application workers
- compose.production.yml - production app stack, including private Prometheus and Grafana monitoring
- go-judge - pinned go-judge and Python sandbox image
- backend - FastAPI on Python 3.14
  - main.py
  - requirements.txt
  - app/core - configuration, database, sessions, permissions, and API errors
  - app/routers - auth, courses, problems, assignments, analytics, and submissions
  - app/services - response shaping and shared analytics formulas
  - app/models - SQLAlchemy application schema
  - migrations - Alembic schema revisions
  - app/worker - durable go-judge execution, recovery, and email delivery
- frontend - Vite + React + strict TypeScript, with login, student problem/statistics, and teacher class/problem/analytics routes
- docs - research notes and tests; the design set is in [docs/design](docs/design/), with D0, D1, D2, user stories, and review notes
- .githooks - versioned pre-commit hook
- pyproject.toml - backend dependencies and Ruff/pytest settings
- uv.lock - reproducible Python dependency lockfile

The [pilot participation form](docs/TECHNIVIEW_CONSENT_FORM.md) also has a
[printable PDF](docs/TECHNIVIEW_CONSENT_FORM.pdf).

## Section 3: Design and test documents

- [Week 9 requirements draft](docs/design/requirements_document.md)
- [Week 9 technical specification draft](docs/design/technical_specification.md)
- [Test plan](docs/Test_Plan.md) ([PDF submission copy](docs/Test_Plan.pdf))

## Section 5: Ethics and attribution

- [Ethics statement](docs/Ethics_Statement.md) ([PDF submission copy](docs/Ethics_Statement.pdf))
- [Revised Assignment #7 constraints essay](docs/Assignment_7_Constraints_Essay.md) ([PDF](docs/Assignment_7_Constraints_Essay.pdf))

TechniView's code and team-created logo are [MIT licensed](LICENSE). The logo at
the top of this README was made by the TechniView team. No generated concept art
ships in the app. The interface uses system fonts and no separate icon pack.
The six D0-D2 diagrams in `docs/design/images/` are TechniView team documentation
assets under the project MIT license.
The team reports no tutorial or other-repository code snippets adapted into the
application beyond the attributed problem catalog.

The 500-problem catalog derives from [APPS](https://github.com/hendrycks/apps)
and [APPS+](https://github.com/Ablustrund/APPS_Plus). Those repositories identify
their datasets as MIT licensed. They collected coding problems from public
challenge sources. TechniView removed duplicate statements, selected problems,
reviewed tests, and retains source metadata and attribution per problem in
`backend/data/problem_catalog.json`. The raw curation scripts are not in this
repository. Source links inside problem statements may point to external media;
those links do not grant a license to redistribute the media.

Directly declared software dependencies and source links follow. Versions are
the ones pinned in `uv.lock` and `frontend/package-lock.json` as of this ethics
statement; production image versions are documented in [runner execution](#runner-execution).
Application libraries are permissively licensed. The separately deployed MySQL
and Grafana services are copyleft and remain under their own licenses. MIT and
BSD-3-Clause require notices to be retained; Apache-2.0 also requires notices
and change marking when applicable. Dependency license text remains with the
installed packages.

| Software and source | Version | SPDX license |
|---|---:|---|
| [FastAPI](https://github.com/fastapi/fastapi), [Alembic](https://github.com/sqlalchemy/alembic), [PyMySQL](https://github.com/PyMySQL/PyMySQL), [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | 0.141.1; 1.16.5; 1.2.0; 2.0.52 | MIT |
| [HTTPX](https://github.com/encode/httpx), [Uvicorn](https://github.com/encode/uvicorn) | 0.28.1; 0.52.4 | BSD-3-Clause |
| [React](https://github.com/facebook/react), [React DOM](https://github.com/facebook/react), [React Router](https://github.com/remix-run/react-router), [Monaco React](https://github.com/suren-atoyan/monaco-react) | 18.3.1; 18.3.1; 7.18.4; 4.7.0 | MIT |
| [ESLint JS](https://github.com/eslint/eslint), [ESLint](https://github.com/eslint/eslint), [ESLint Config Prettier](https://github.com/prettier/eslint-config-prettier) | 10.0.1; 10.10.0; 10.1.8 | MIT |
| [React Hooks ESLint](https://github.com/facebook/react), [React Refresh ESLint](https://github.com/ArnaudBarre/eslint-plugin-react-refresh) | 7.1.1; 0.5.6 | MIT |
| [Testing Library React](https://github.com/testing-library/react-testing-library), [React types](https://github.com/DefinitelyTyped/DefinitelyTyped), [React DOM types](https://github.com/DefinitelyTyped/DefinitelyTyped) | 16.3.3; 18.3.31; 18.3.7 | MIT |
| [Vite React plugin](https://github.com/vitejs/vite-plugin-react), [Vite](https://github.com/vitejs/vite), [Vitest](https://github.com/vitest-dev/vitest) | 5.2.0; 8.3.5; 5.0.5 | MIT |
| [jsdom](https://github.com/jsdom/jsdom), [Prettier](https://github.com/prettier/prettier), [globals](https://github.com/sindresorhus/globals), [typescript-eslint](https://github.com/typescript-eslint/typescript-eslint) | 27.4.0; 3.9.6; 17.12.0; 8.69.0 | MIT |
| [TypeScript](https://github.com/microsoft/TypeScript) | 6.0.3 | Apache-2.0 |
| [pip-audit](https://github.com/pypa/pip-audit), [pre-commit](https://github.com/pre-commit/pre-commit), [pytest](https://github.com/pytest-dev/pytest), [pytest-cov](https://github.com/pytest-dev/pytest-cov), [Ruff](https://github.com/astral-sh/ruff) | 2.10.1; 4.6.2; 9.1.1; 7.1.0; 0.13.3 | Apache-2.0; MIT; MIT; MIT; MIT |
| [go-judge](https://github.com/criyle/go-judge), [Caddy](https://github.com/caddyserver/caddy), [Prometheus](https://github.com/prometheus/prometheus) | 1.13.3; pinned image digest; 3.3.1 | MIT; Apache-2.0; Apache-2.0 |
| [MySQL Community](https://www.mysql.com/products/community/), [Grafana](https://github.com/grafana/grafana) | 8.0; 11.6.0 | GPL-2.0-only; AGPL-3.0-only |
| [Python](https://github.com/python/cpython), [Node.js](https://github.com/nodejs/node) | 3.14; pinned image digest | PSF-2.0; MIT |

## Config

Secrets live in `.env`, which is gitignored. Copy the template and change values:

```
cp .env.example .env
```

Compose works without `.env` too, it falls back to dev defaults.

go-judge executes Python 3.14 in a fresh sandbox for each case. The application
worker records each case attempt in MySQL before execution and stores the result
when go-judge returns. If a worker dies after dispatch, recovery records an
unknown outcome instead of running the case again. The runner needs Linux cgroup
v2 and a privileged container to create per-execution cgroups. go-judge uses
`-no-fallback`, so it stops if cgroup setup fails. Sandboxed programs run with
UID and GID 1536, no effective capabilities, the built-in seccomp filter, and
an isolated network namespace. See [runner decision and evidence](docs/runner-decision.md)
for the controls and the remaining privileged-container risk.

## Dev setup

You need hooks for formatting and tests. They live in `.githooks` and are shared
through Git config. Install [uv](https://docs.astral.sh/uv/), then run `make install`
after cloning. It creates the locked Python environment, installs frontend
dependencies, and turns the hooks on. Hooks run checks only. They do not install
tools or rewrite files.

`make check` runs the local checks. `make verify` also builds the frontend and
runs the temporary MySQL/go-judge integration suite. The checks are:

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
make integration # disposable MySQL + go-judge integration stack (requires Docker)
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
worker executes cases through go-judge and persists results in MySQL.
`POST /api/problems/{id}/run` uses public cases and does not consume a graded
attempt. Submit uses all server-owned cases. Both POST routes require an
`Idempotency-Key`; the browser reuses the key after a network failure and clears
it after a successful response. Keys expire after 24 hours. A new key starts a
new run, even when the source code is unchanged. Keep `app_worker` running
alongside the API. Course enrollment, email verification, and password recovery
use an email outbox; local Compose captures messages in the worker at
`/tmp/techniview-mail`. For hosted delivery, set `EMAIL_DELIVERY_MODE=resend`,
`EMAIL_SIGNING_KEY`, `EMAIL_FROM`, `RESEND_API_KEY`, and `PUBLIC_APP_URL` on both
API and worker. See [course and account setup](docs/course-accounts.md).

Course summaries update with grading transactions. Set a stable
`RESEARCH_EXPORT_SECRET` of at least 32 bytes before producing a research CSV.
See [backend reporting](docs/backend-reporting.md) for export fields and the
offline progress rebuild procedure. The [database recovery guide](docs/database-recovery.md)
has the Compose backup and restore steps.

`make integration` runs migrations against a fresh MySQL database and executes
real Python cases through go-judge. The stack has no host ports or persistent
database storage, does not read `.env`, and removes its containers on exit.

For a hosted installation, use [the campus deployment guide](docs/deployment.md).
Production uses separate application and runner VMs. The application Compose
stack serves HTTPS and keeps MySQL off host ports. go-judge binds only to the
runner VM's private interface.

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

The [go-judge image](go-judge/Dockerfile) pins go-judge 1.13.3 and Python 3.14.8.
The application owns the submission queue, attempt records, grading, and recovery.
The runner VM owns sandbox execution only. The default is 16 go-judge execution
slots and four application worker processes per application worker container.
`GO_JUDGE_PARALLELISM` and `DIRECT_WORKER_PROCESSES` set those limits. CPU quota is
a ceiling, not an exclusive core reservation.

The app worker records each attempt before sending it to go-judge. If the worker
dies while a case may have run, recovery marks that case as an infrastructure
failure and never silently reruns it. The student can start a new submission.

See [runner decision and evidence](docs/runner-decision.md) for the benchmark
history and [testing](docs/testing.md) for integration checks.

## Appendix

The [test plan](docs/Test_Plan.md) maps the Week 9 requirements to runnable cases,
staging conditions, acceptance thresholds, and the spring pilot gates.
