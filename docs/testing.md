# Testing and CI

TechniView has three test layers. Use the first two during normal development. Use
the third before opening a backend or infrastructure PR.

## First-time setup

Install uv, Node.js 22, Docker, and Git. uv manages Python 3.14 and the backend
virtual environment for you. Then run:

```sh
make install
```

This installs the locked backend environment in `.venv`, the frontend dependencies,
and configures the tracked pre-commit hook. Copy `.env.example` to `.env` only when
you need to change local Compose settings. The integration tests do not read `.env`.

Run backend commands through uv so every developer uses the lockfile:

```sh
uv run python -m pytest -q
uv run ruff check backend
uv run ruff format --check backend
```

## Development database reset

This pre-production branch changes the initial schema for execution snapshots.
Existing development databases must be recreated before running this branch;
`alembic upgrade head` alone cannot update a database that already applied the
initial migration. Export anything you want to keep before recreating your local
database. The integration stack creates a fresh database on every run.

Each queued case stores its inputs, generated Python program, expected output,
visibility, and resource limits. Editing a draft changes future runs only.
Queued, running, and completed results keep the values captured when submitted.

## Local checks

`make check` runs the checks used for every commit:

- Ruff lint and formatting checks
- Backend pytest
- Frontend TypeScript, ESLint, Prettier, and Vitest

`make build` runs the frontend production build. `make verify` runs `make check`,
the production build, and the temporary MySQL/Judge0 integration stack.

Run one area while debugging:

```sh
uv run python -m pytest -q
uv run python -m pytest -q backend/tests/test_submissions.py
cd frontend && npm test
cd frontend && npm run build
```

Formatting commands edit files. Use them deliberately:

```sh
make fmt
```

The commit hook only checks files. It never installs tools or rewrites the
working tree. If it says uv or a Python tool is missing, run `make install`.

## Integration tests

`make integration` builds the local API and Python-only worker images from
`internal-judge0-fork/` and starts a temporary Compose project with MySQL
8, Judge0, Judge0 workers, Redis, Postgres, the API, and the application worker. It runs migrations
against a fresh database and then removes the containers, network, and volumes
when it exits. See
[`internal-judge0-fork/README.md`](../internal-judge0-fork/README.md)
for image build and update details.

The integration suite checks the parts SQLite and mocks cannot prove:

- MySQL migrations and encoded credentials
- MySQL REPEATABLE READ callback races
- Duplicate callback delivery and progress counting
- Real accepted, wrong-answer, and runtime-error Judge0 submissions
- Python submissions without a caller-supplied Judge0 language ID
- CPU, memory, output size, filesystem and network sandbox limits
- Rejected language selection, archive uploads and network enablement
- Completion through callbacks without API polling
- Polling recovery when no callback arrives
- Asynchronous submission dispatch by the application worker
- UTF-8 source-size validation through the HTTP API
- Fifty concurrent students submitting the same problem, with one durable result
  and one Judge0 case per request

On October 14, 2026, the clean disposable stack passed all eight integration
checks, including the fifty-request burst, on Linux x86_64 with 16 logical CPUs,
23 GiB RAM, and Docker 29.9.0. The burst completed in the test's 120-second
deadline. This is a local concurrency check, not a hosted capacity guarantee.

Judge0 uses privileged cgroup access in this disposable stack because the runner
needs the same sandbox controls as local development. Do not point it at a
personal database or production service.

## Load test

The CI integration job runs `make load-test` on a standard Ubuntu 24.04
GitHub-hosted runner. It drives the disposable MySQL/Judge0 stack with a
synchronized burst of 100 students submitting one published assignment item.
Each submission runs one real sandbox case. The test prepares the assignment and
accounts before timing the burst, then waits for every submission and case to
finish. The test starts four application workers and four Judge0 worker
processes. It reports configured worker counts, API acceptance and completion
latency percentiles, throughput, failures, maximum application queue depth and
age, observed case counts in each dispatch phase, and live Judge0 worker states
and queue depth from Judge0's `/workers` endpoint. It samples that endpoint
every 200 ms and reports peak and average busy workers. Metrics scrape errors
fail the run, as does failure to observe the configured Judge0 worker processes.
No latency or throughput threshold is enforced until repeatable baselines have
been collected. The integration CI job has a 60-minute budget and the load run
has a 20-minute completion deadline.

The runner profile is recorded in the CI log with each run. GitHub-hosted runners
use standardized VM classes, but the underlying host can still vary; compare
results alongside that profile. The test target can be run manually for debugging,
but treat GitHub Actions runs as the comparable baseline:

```sh
make load-test
```

The test can vary simultaneous students, request concurrency, cases per
submission, application worker replicas, and Judge0 worker processes. Keep all
but one setting fixed when comparing profiles. For example, start with the CI
default, then change Judge0 worker count, then test a larger case set:

```sh
make load-test
make load-test LOAD_JUDGE0_WORKERS=8
make load-test LOAD_CASES_PER_SUBMISSION=5
```

To test a larger burst, increase both student count and request concurrency,
for example `make load-test LOAD_STUDENTS=250 LOAD_CONCURRENCY=250`.

Use the manually dispatched `Worker capacity sweep` workflow to compare 1, 2, 4,
and 8 Judge0 workers, then 1, 2, 4, and 8 application workers. It runs each
profile three times, sequentially, on one standard `ubuntu-24.04` host with 100
simultaneous students and one case per submission. The JSON results and per-run
logs are saved as a 30-day Actions artifact. This workflow does not request a
larger runner; it uses the repository's normal GitHub Actions allowance.

Change one factor at a time and repeat each profile at least three times. Keep
the standard GitHub runner size fixed for CI comparisons. These targets do not
request a larger or paid runner, but Actions billing still depends on repository
visibility, plan, and remaining included minutes. Do not add repeated profiles
to every pull request until the repository's Actions spending controls are
confirmed. Use the campus VMs to establish the final capacity claim against the
proposed split app and runner topology.

This measures the full application and runner stack on the host running Docker.
GitHub-hosted CI results are regression baselines, not a campus capacity claim.
Before using results for VM sizing, repeat the profile on the proposed campus VM
sizes with the expected student count and problem mix. Never point the load test
at a production service.

## GitHub checks

Every pull request runs five parallel jobs:

- Workflow checks run actionlint and ShellCheck.
- Backend checks run Ruff, pytest with branch coverage output, and pip-audit.
- Frontend checks run npm audit, TypeScript, ESLint, Prettier, Vitest, and the
  production build.
- Integration runs `make integration` and the 100-student, one-case
  `make load-test` on a clean Ubuntu runner.
- Production images builds the API, frontend, and runner images used on campus.

The final `CI` check fails if any job fails, is cancelled, or is skipped. That is
the check that should be required by the `main` branch ruleset. A workflow-only
change still runs the workflow checks.

A `v*` tag publishes the reviewed production images to GitHub Container Registry
after the full CI gate passes. Each image is tagged with the source commit SHA.

## Adding tests

Put fast application tests in `backend/tests` or beside the relevant frontend
component. Keep external services out of those tests by using the existing test
fixtures and mocks. Put tests that need MySQL, Judge0, Docker networking, or
real callback delivery in `backend/integration`.

When adding behavior, test its successful path, its permission or validation
boundary, and the failure that would leave persisted state inconsistent. Prefer
one parameterized test when cases share setup and assertions. Update this guide
when a new command, service, or CI job changes the developer workflow.

## CI failure workflow

Start with the failing job name. Run its local equivalent before changing code:

```sh
make check       # Backend or frontend checks
make build       # Frontend build failure
make integration # MySQL, Judge0, Docker, or callback failure
```

For integration failures, preserve the service logs from the failed run before
rerunning. The Compose command cleans up automatically, so a second run starts
with a new database and new Judge0 queue.

## Problem authoring and question sets

The authoring API is available to professor accounts. Create/edit custom draft problems with nested `tags` and ordered `test_cases`; use the validate endpoint to run the canonical solution against every case before publishing. Copy a visible problem to start a separate custom draft. Hidden cases and canonical source are intentionally excluded from ordinary problem detail responses.

Question sets are private to their owner. Replace their ordered contents with `PUT /api/question-sets/{id}/items`, then publish them. Creating an assignment from a published question set snapshots its ordered problem IDs into assignment items, so later edits to the source set do not affect the assignment.
