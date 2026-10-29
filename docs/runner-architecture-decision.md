# Runner architecture decision

2026-10-29, revised after inspecting worker startup and earlier Isolate results. Decision: retain Judge0/Isolate while evaluating its existing orchestration improvements. The evidence does not yet justify replacing it. The direct integration proposal below is a deferred alternative, not approved implementation work.

The final A100 comparison enabled grouping, persistent Ruby workers and HTTP reuse only for the go-judge candidate (`scripts/runner-bench.py`, paired_engine_group_persistent branch). Its baseline used base Compose. Consequently this was not an equal-configuration engine comparison.

Existing local `persistent-isolate-screen/comparison.md` results show persistent workers reduced API p50 by 58–62% at concurrency one and 36–72% at concurrency ten across three repetitions. These are local screening results, not A100 forecasts. Grouping alone was mixed. The optimized Isolate path merits evaluation before any rewrite.

Concurrency is already implemented: `worker_supervisor.rb` spawns COUNT separate Resque processes. Isolate execution holds a per-sandbox slot lock, not one global execution lock. Group jobs process cases sequentially within a submission, while separate workers can process different submissions simultaneously. The go-judge launcher also sets its parallelism to COUNT. No permanent per-worker CPU affinity is required for these processes to execute in parallel.

Docker's cpus setting controls aggregate CPU quota; cpuset controls eligible logical CPUs. Neither setting alone reserves exclusive physical cores on a shared host. With 16 runnable single-threaded jobs and sufficient available logical CPUs, the scheduler can run all 16 simultaneously. The 24 CPU allowance supplies aggregate headroom; the backend and application workers have separate limits. See https://docs.docker.com/engine/containers/resource_constraints/ and https://github.com/resque/resque.

No new load tests were run during this review. The next test, if needed, is a small equal-configuration engine comparison using the existing adapters. A direct integration rewrite and separate CPU saturation campaign are deferred. Configuration establishes concurrency capability; actual overlap and utilization remain runtime observations.

## What actually ran

The final candidate was a hybrid. TechniView submitted grouped cases to the forked Judge0 Rails API. PostgreSQL held runner records and Redis held runner jobs. Persistent Ruby workers processed each group's cases sequentially and called go-judge over HTTP. Go-judge created fresh sandboxes and Python processes. Results went back through the runner persistence and callback path.

See `compose.go-judge-shared.yml`, `internal-judge0-fork/experiments/go-judge-workers.sh`, `internal-judge0-fork/api/app/jobs/group_job.rb`, and `internal-judge0-fork/api/app/helpers/go_judge_executor.rb`. The launcher explicitly starts both Go and Ruby processes.

Standalone execution tests exist in `benchmark-results/local-runner/go-judge-direct-final/`. They do not constitute a standalone go-judge implementation of the public submission API.

## Evidence and limits

- The A100 ungrouped engine comparison made go-judge slower in every measured API pair. Replacing the sandbox engine inside the old per-case orchestration was insufficient. See `benchmark-results/local-runner/a100-engine-ab-imported/FINDINGS.md`.
- The local combined screen found dispatch concurrency four regressed at 25 submissions in all three repetitions. Do not carry that setting forward automatically. See `benchmark-results/local-runner/combined-results/REPORT.md`.
- The completed final capacity campaign has 18 cells and nine pairs each. The grouped go-judge hybrid was substantially faster under concurrent submission load, while single-submission results sometimes favored Judge0. This supports the combined implementation, not a claim that go-judge alone caused the gain.
- At 24 CPUs and 16 workers, medians across the nine workload/repetition burst p50s were approximately 7.19 seconds at concurrency 10 and 14.06 seconds at concurrency 25. Corresponding baseline medians were 13.42 and 28.96 seconds. These are medians of burst statistics, not pooled submission percentiles.
- Worker resource reports measure CPU time divided by sampled wall time for the Compose `workers` service, then summarize across bursts. They exclude other services and are not peak CPU utilization. Validate sandbox cgroup ancestry before treating these counters as proof of total execution demand. An average around 2.5 cores does not establish the absence of short CPU bottlenecks or upstream starvation.
- The campaign did test 16 workers with a 24 CPU quota. Linux can schedule 16 runnable processes on 16 logical CPUs without permanent core pinning. The earlier conversation incorrectly implied that workers need explicit core assignment to execute in parallel.

## Deferred direct-integration alternative

Public API -> existing durable application submission records -> application execution workers -> private go-judge service -> application case results and grading progress.

Use the application's database as the authoritative owner of submissions, cases, attempts and completion. Reuse and extend its existing claim/idempotency mechanisms. Remove the second runner database, Rails API, Ruby job workers and runner-specific Redis dependency after migration. Do not remove application dependencies merely because the runner stops using them.

Go-judge supplies sandbox execution and resource reports. TechniView must continue owning durable scheduling, recovery, expected outputs, verdict calculation and progress. A bare go-judge endpoint is not a replacement for those responsibilities. See https://github.com/criyle/go-judge and the pinned v1.13.3 command model at https://pkg.go.dev/github.com/criyle/go-judge@v1.13.3/cmd/go-judge/model.

Keep fresh Python and sandbox state for every case. Use one durable submission job with individual durable case attempt records. Bound active execution requests globally across workers; do not accidentally multiply concurrency by the app-worker count. Begin with 16 execution slots and the requested 24 CPU ceiling for comparability, retaining the existing 8 GiB memory ceiling and per-case limits. CPU quota is a ceiling, not a reservation. Host core exclusivity requires an allocation agreement on the shared server; affinity alone is not exclusivity.

Reuse managed HTTP clients. Persist an attempt before dispatch, perform execution outside database transactions, and fence result updates by attempt identity. A lost response or worker crash after dispatch must produce an explicit unknown outcome; never silently execute student code again. Recover unstarted cases separately. Preserve duplicate request handling and partial progress. Direct synchronous execution responses eliminate the runner callback hop, but do not eliminate ambiguous outcomes.

## Deferred validation for a direct-integration migration

Implement the adapter and durable attempt transitions first. Then run:

1. Focused correctness and failure checks: both problem styles; all canonical cases; isolation between cases; wrong answers, exceptions, fatal exits, CPU/memory/output limits; duplicate requests; worker restart and lost execution response. Confirm durable progress and no automatic re-execution of an uncertain attempt.
2. One short CPU accounting probe with 16 independent CPU-bound cases: verify overlapping execution, cgroup ancestry, aggregate quota and per-case enforcement. Measure CPU usage only over the busy interval. This answers the core-utilization question without another workload matrix.
3. Three paired Ransom Note bursts at concurrency 10 and 25, comparing the verified hybrid with the direct path at 16 slots/24 CPUs. One warm-up per profile, fixed 200 ms result polling, five-minute burst deadlines and existing host safety stops. Check the other two workloads for correctness once.

Budget roughly 30–60 minutes of server testing after builds and implementation, subject to existing verifier duration. Stop on correctness or accounting failures; do not launch an overnight matrix. Preserve raw samples and resource data. Switch only after correctness/recovery checks pass and the paired results show no material unexplained regression. Keep the public API stable and retain a rollback configuration.
