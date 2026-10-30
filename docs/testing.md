# Testing and CI

Install uv, Node.js 22, Docker, and Git, then run `make install`. The tracked
pre-commit hook runs local checks without rewriting files.

- `make check` runs Ruff, backend pytest, TypeScript, ESLint, Prettier, and Vitest.
- `make build` builds the frontend.
- `make integration` builds a disposable MySQL and go-judge stack and runs real
  Python submissions, sandbox limit checks, idempotency checks, and a 50-student
  request burst. It removes the stack on exit and does not read `.env`.
- `make load-test` runs a synchronized 100-student, one-case burst through that
  stack. Set `LOAD_STUDENTS`, `LOAD_CONCURRENCY`, `LOAD_CASES_PER_SUBMISSION`,
  `LOAD_APP_WORKERS`, `DIRECT_WORKER_PROCESSES`, and `GO_JUDGE_PARALLELISM` to
  explore other profiles. Results include API latency, completion latency, queue
  depth, and persisted case counts. CI results are regression baselines, not a
  campus capacity claim.
- `scripts/verify-direct-runner.sh` kills an application worker during execution
  and verifies that recovery records an unknown outcome without a second run.

`make verify` runs checks, frontend build, and integration. Backend and production
image builds run in CI. Every pull request must pass the final `CI` gate.

The integration stack uses privileged cgroup access for go-judge. Keep it on a
disposable database; the test asserts its database name before running a load
burst. Compare production capacity only on the allocated application and runner
VMs with the expected student count and problem mix.
