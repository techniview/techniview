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
- Pull request CI compares the base and proposed backend on the same
  `ubuntu-24.04` host. It gives each revision and workload a fresh disposable
  database, runs a five-student warm-up, then takes three 100-student
  measurements at matching worker settings. Workload definitions live in
  `backend/performance/workloads/v1.json`. The `short`, `cpu-heavy`, and
  `multi-case` workloads are fixed inputs; `multi-case` runs 25 cases per
  submission. Reports include source code and cases, image IDs, commit, host
  and worker profile, completion and queue-wait percentiles, batch time,
  throughput, case counts, and p95 case CPU time as a fraction of its CPU
  limit. The CPU-heavy case sums 4,999-by-4,999 modular products with a
  three-second case limit. CI fails a workload only when median batch time
  is both more than 50 percent and more than two seconds slower than base. It
  compares each workload on its own and never combines results into one score.
  CI uploads base and proposed reports even when a run fails. If a new branch
  points at the same commit as `main`, CI writes a comparison artifact with a
  skip reason instead of trying to benchmark one revision against itself.
- To reproduce a comparison locally, create a base worktree and run:

  ```sh
  make performance-compare PERF_BASE_PATH=/path/to/base \
    PERF_BASE_COMMIT=<base-sha> PERF_PROPOSED_COMMIT=<proposed-sha>
  ```

  Reports go to `/tmp/techniview-performance` unless `PERF_OUTPUT_DIR` is set.
  Set `PERF_RUNNER_CPU_LIMIT`, `PERF_RUNNER_MEMORY_LIMIT`,
  `PERF_API_DB_POOL_SIZE`, `PERF_WORKER_DB_POOL_SIZE`, and
  `PERF_DB_MAX_OVERFLOW` to match target service limits. This command builds and
  removes uniquely named Compose projects; do not run it alongside another
  benchmark on the same Docker daemon.
- `scripts/verify-direct-runner.sh` kills an application worker during execution
  and verifies that recovery records an unknown outcome without a second run.

`make verify` runs checks, frontend build, and integration. Backend and production
image builds run in CI. Every pull request must pass the final `CI` gate.

The integration stack uses privileged cgroup access for go-judge. Keep it on a
disposable database; the test asserts its database name before running a load
burst.

For capacity planning, start with a disposable staging environment on the
target VM class. Match the planned application worker replicas, direct worker
process count, go-judge slots, runner CPU and memory limits, and database pool
settings. The reports record those settings. Run the 100-student,
25-case workload first. Then build a representative staging assignment from the
short, CPU-heavy, and multi-case v1 definitions, with case counts based on the
expected assignment mix. Submit that cohort concurrently and retain separate
per-workload measurements. The CI comparison runs isolated cohorts; it does
not measure cross-workload queue interaction. Repeat the target run at higher
concurrency until latency, queue age, failures, or host limits no longer meet
the campus target. Save workload version, VM shape, service limits, expected
workload shares, and raw reports with the capacity decision. CI runs on
GitHub-hosted hardware and cannot establish capacity for campus VMs.

The submission grader runs Python cases on CPU through go-judge. A GPU used by
the optional Ollama complexity service is not part of these measurements.
Measure that service separately on the target GPU host. Use the deployed model,
context length, and analysis-request share; run that request rate while the
submission mix is active. Record GPU model and memory, Ollama queue and latency
percentiles, timeouts, and GPU memory use. Do not make a campus capacity claim
until these runs have completed on the target hosts.
