# Testing and CI

TechniView has three test layers. Use the first two during normal development. Use
the third before opening a backend or infrastructure PR.

## First-time setup

Install Python 3.14, Node.js 20, Docker, and Git. Then run:

```sh
make install
```

This installs the backend and frontend dependencies and configures the tracked
pre-commit hook. Copy `.env.example` to `.env` only when you need to change local
Compose settings. The integration tests do not read `.env`.

## Local checks

`make check` runs the checks that should be fast enough for every commit:

- Ruff lint and formatting checks
- Backend pytest
- Frontend TypeScript, ESLint, Prettier, and Vitest

`make build` runs the frontend production build. `make verify` runs `make check`,
the production build, and the disposable MySQL/Judge0 integration stack.

Run one area while debugging:

```sh
cd backend && python -m pytest -q
cd backend && python -m pytest -q tests/test_submissions.py
cd frontend && npm test
cd frontend && npm run build
```

Formatting commands edit files. Use them deliberately:

```sh
make fmt
```

The commit hook only checks files. It never installs tools or rewrites the
working tree. If it says a tool is missing, run `make install`.

## Integration tests

`make integration` starts a temporary Compose project with MySQL 8, Judge0,
Judge0 workers, Redis, Postgres, and the API. It runs migrations against a fresh
database and then removes the containers, network, and volumes when it exits.

The integration suite checks the parts SQLite and mocks cannot prove:

- MySQL migrations and encoded credentials
- MySQL REPEATABLE READ callback races
- Duplicate callback delivery and progress counting
- Real accepted, wrong-answer, and runtime-error Judge0 submissions
- Completion through callbacks without API polling
- Polling recovery when no callback arrives
- UTF-8 source-size validation through the HTTP API

Judge0 uses privileged cgroup access in this disposable stack because the runner
needs the same sandbox controls as local development. Do not point it at a
personal database or production service.

## GitHub checks

Every pull request runs four parallel jobs:

- Workflow checks run actionlint and ShellCheck.
- Backend checks run Ruff, pytest with branch coverage output, and pip-audit.
- Frontend checks run npm audit, TypeScript, ESLint, Prettier, Vitest, and the
  production build.
- Integration runs `make integration` on a clean Ubuntu runner.

The final `CI` check fails if any job fails, is cancelled, or is skipped. That is
the check that should be required by the `main` branch ruleset. A workflow-only
change still runs the workflow checks.

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
