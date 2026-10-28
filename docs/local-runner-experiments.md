# Local runner experiments

This document retains the local runner experiment history. For the current
A100-host findings, see the [Judge0 versus go-judge comparison](../benchmark-results/local-runner/a100-engine-ab-imported/FINDINGS.md)
and the [final combined-profile runbook](a100-wrap-up-testing-runbook.md).
The original local combined matrix and independent experiment results are
summarized in the [selected matrix findings](../benchmark-results/local-runner/selected-matrix/FINDINGS.md)
and the [resumed experiments report](../benchmark-results/local-runner/resume/REPORT.md).

## Measurement

`backend/performance/load_test.py` accepts `LOAD_PROBLEM` with a catalog title.
It copies the canonical solution and every stored case into the disposable
assignment scenario. The three planned workloads have 34, 34, and 35 cases.
Synthetic workloads remain available for existing CI callers.

The main duration uses the load client's monotonic clock, from starting POST
`/api/submissions` to receiving a terminal GET response. Each submission polls
with a fixed 200 ms sleep between requests. Request time is additional to that
sleep. Acceptance durations use the same clock. The five-minute deadline begins
at the burst's start; account and problem preparation happen first.

Reports retain server submission/completion timestamps separately. MySQL now
stores microseconds for those two fields. Their difference is a server event
interval, rather than the client's turnaround duration. Do not subtract a client
wall clock from a server wall clock to infer retrieval delay. The first baseline
predates the precision migration and has whole-second server timestamps.

The load test checks passed API verdicts and case counts, then checks durable
submission and case records independently. Raw completion samples, metrics,
runner worker snapshots, host memory, swap, Docker resource samples, and cgroup
CPU/memory counters form the report inputs. Failed bursts remain incomplete.
Future runs also save durable execution state before deleting the database.
Transient Prometheus and worker-status scrape errors are retained as telemetry
errors rather than discarding a burst whose submissions completed correctly; a
run with no worker-status samples is still incomplete. Resumed sessions keep
their own source diff and record the prior diff hash in session metadata.

Runner stage instrumentation uses a monotonic clock around Isolate initialization,
execution, cleanup, result persistence, and inline callback delivery. The first
HTTP pairs used an INFO logger suppressed by the runner's WARN log level; their
stage samples are missing. The instrumentation now emits at the active level
only when `RUNNER_BENCHMARK_TIMINGS=1`.

## Profiles and commands

`compose.benchmark.yml` overlays the disposable integration stack. The execution
container is limited to 6 CPUs, 8 GiB RAM, and no additional swap. The file also
bounds every other service. Each report records its limits and worker counts.

Build outside timing:

```sh
docker compose --env-file /dev/null -p techniview-runner-bench \
  -f compose.integration.yml -f compose.benchmark.yml \
  build backend tests app_worker judge workers
```

Use a unique label for each run. The original memory and swap guards remain active.

```sh
python scripts/runner-bench.py --label baseline-next
python scripts/runner-bench.py --label http-next --paired-http
python scripts/runner-bench.py --label outbox-next --paired-outbox
python scripts/runner-bench.py --label dispatch-next --paired-dispatch --dispatch-concurrency 4
python scripts/runner-bench.py --label go-next --paired-engine-shared
python scripts/runner-bench.py --label combined-ransom-w8 --paired-combined --combined-ablation --dispatch-concurrency 4 --problem "Ransom Note" --workers 8 --concurrency 1 10 25 --repetitions 3
python scripts/compare-runner-bench.py benchmark-results/local-runner/http-next
```

The driver defaults to 8 execution workers, 4 application workers, concurrency
1 and 10, one warm-up per profile, and three repetitions. Paired runs alternate
profiles and warm each profile before timing. `--problem`, `--workers`,
`--concurrency`, and `--repetitions` select subsequent measurements. Use unique
labels; existing evidence is never overwritten.

The host memory guard samples separately from Docker stats collection. It stops
a burst after five seconds below 2 GiB available memory, or swap growth greater
than 512 MiB from that burst's initial usage. The API burst itself has a
five-minute deadline. A separate host watchdog permits preparation time before
terminating an unresponsive test container. An incomplete burst stops the driver.

The driver removes only its explicit Compose project's resources. Reports live
in `benchmark-results/local-runner`, outside disposable database storage. They
include the source commit, tracked diff, hashes, machine and Docker versions,
container image IDs, and service limits. New runs also retain untracked source
files and a complete source hash manifest.

## A100 campaigns

The grouped-job and persistent-worker comparison completed all three problems
at 8 and 16 workers. A later engine-only comparison completed all three
problems with 8 workers. These results are stored under
`benchmark-results/local-runner/a100-group-persistent-imported/` and
`benchmark-results/local-runner/a100-engine-ab-imported/`.

The remaining paired test compares Judge0 with grouped, persistent go-judge.
Use the [final runbook](a100-wrap-up-testing-runbook.md). It runs the
profile-specific integration checks before the API performance matrix and
records progress in a campaign manifest.

## Implemented candidates

HTTP pooling is explicit with `JUDGE0_REUSE_CONNECTIONS=1`. Each application
worker owns a client until shutdown and closes it when leaving the worker loop.
Request timeouts remain per request. Database session ownership is unchanged.
The default keeps the existing per-request client lifetime.

The runner callback outbox is explicit with `RUNNER_CALLBACK_OUTBOX=1`.
Execution results and a unique delivery record commit in one PostgreSQL
transaction. The optional `callbacks` service locks due records with
`FOR UPDATE SKIP LOCKED`, sends the stored payload, and records the outcome.
Retries have exponential delays capped at 60 seconds and stop after eight
attempts. An exhausted delivery remains inspectable. Polling recovery remains
available to the application.

A delivery worker never invokes execution. If a process dies after a successful
HTTP call but before commit, another worker can deliver the callback again.
The application must therefore continue accepting duplicate results idempotently.
The outbox's resource cost includes the additional callback service and persisted
payloads. No maintenance or performance advantage has been established yet.

## Verification and remaining work

`scripts/verify-runner-experiments.sh` runs the real integration and sandbox checks
with one runner worker. It excludes the existing 50-submission load test under
the safety stop. It also checks outbox rejection, ambiguous delivery, delay,
duplicate suppression, exhaustion, transaction rollback, and recovery in a new
process. These checks do not establish performance.

The catalog workload tests run all 103 canonical cases through the production
execution wrapper on local Python, in separate processes. This verifies fixture
correctness. The earlier go-judge-plus-pooling API matrix covered all three
workloads at 1/10/25 submissions with 8/16 runner workers. The separate grouped
job plus persistent-worker matrix is partial; its completed Ransom Note results
and safety stop are summarized above.

The resumed phase completed independent HTTP, outbox, dispatch, and go-judge
comparisons at concurrency 1 and 10, each with three paired repetitions. Raw
samples and paired absolute/percentage differences are in the result folders.
Grouping and persistent workers have now been evaluated together on Ransom Note
at c1/c10 for both worker counts and c25 with 8 workers. Shared Python was
rejected after the isolation leak. The planned grouped runs for the other two
problems and 16-worker c25 remain unmeasured after the safety stop. No default
engine, worker count, or execution model was changed.

## Concurrent dispatch

`WORKER_DISPATCH_CONCURRENCY` defaults to 1. The measured candidate uses 4.
Threads own separate SQLAlchemy sessions. A worker's managed HTTP client can be
shared through copied context when pooling is explicitly combined later. The worker retains its claim until all case tasks finish. Unexpected worker
errors recover through the existing lease. Ambiguous dispatches keep the existing
no-resubmission recovery policy.

## Grouped jobs and persistent runner workers

`--paired-group-persistent` compares the existing per-case Go-judge path with
the same engine and pooled HTTP client, grouping a submission's cases into one
internal job and reusing bounded Ruby workers. The public API and fresh Python
process per case are preserved. This is a combined candidate comparison; it
does not isolate grouping from worker reuse.

For Ransom Note with 8 workers, the candidate's API p50 improved in all three
c10 pairs by 38-70%, and in all three c25 pairs by 45-70%. At c1 it was faster
in two pairs and 3.9% slower in one. At 16 workers, the completed c1/c10 pairs
also favored the candidate; their p50 changes ranged from -0.5% to -29.5% at
c1 and -50.5% to -71.6% at c10. These are local paired results, not a claim
that 16 workers are better: both counts share the same 6-CPU runner budget.
The w16 c25 attempt was stopped incomplete and is excluded from the comparison.

The planned grouped-worker runs for Number of Islands and Minimum Cost for
Tickets, and the remaining 16-worker Ransom Note c25 repetitions, were not run.
The campaign began at 1,958 MiB swap in use and had reached 2,857 MiB; growth
exceeded the 512 MiB campaign safety limit. The active c25 burst was stopped,
its partial samples remain marked incomplete, and the dedicated Compose project
was removed. No further load was run on this host. A fresh campaign should start
only after the host swap level has recovered and must use a new label.

The shared-Python submission profile remains test-only. A malicious background
thread was able to read a later case's input through inherited file descriptor
state, so that mode does not preserve fresh-case isolation and is rejected as a
production candidate. Ordinary exceptions and fatal exits are represented
explicitly, but that does not address the cross-case input leak.

## Go-judge profiles

The experiment pins [go-judge 1.13.3](https://github.com/criyle/go-judge/releases/tag/v1.13.3)
by binary checksum. It uses the exact Python binary and runtime from the existing
worker image. The current binary packaging targets the tested local amd64 host;
DGX architecture and deployment packaging are not verified yet.

The direct comparison sends identical prepared sources, inputs and limits to
both engines. Isolate's case API requires polling, while go-judge returns its
execution result synchronously. Case API batch times therefore include different
retrieval mechanisms. Engine CPU accounting also differs. Neither measurement
is a substitute for the student submission API comparison.

The integration preserves the existing internal submission interface and retains
Ruby, Redis and PostgreSQL. It replaces sandbox execution, not the entire
control plane. Its CPU and maintenance costs must include those components.

`compose.go-judge-experiment.yml` is the separate-container profile. Its fixed
3/3 CPU split left the Ruby broker throttled while go-judge had unused capacity;
that configuration regressed. `compose.go-judge-shared.yml` runs the same broker
and engine inside one 6 CPU / 8 GiB container so both can use available capacity.
It keeps eight execution workers and fresh Python execution for every case.
`--paired-engine-shared` measures it against the current engine; all other
candidate features stay disabled.

The output adapter bounds each returned stream to the case byte budget, including
when go-judge returns an overflow byte. The CPU extra-time allowance affects the
hard termination budget, while the configured CPU limit still determines whether
a normally completed result is TLE. A real case reproduced the former false-pass
bug and now passes the regression check on both engines.

An interrupted execution is never resubmitted automatically. A durable internal
failure code survives polling and callbacks and maps to the existing public
`runner_outcome_unknown` response. Explicit student retries remain possible.
Tests cover an actual go-judge crash during execution and successful new work
after restart. CPU/memory accounting, process limits and the broader restart and
adversarial matrix still require review before changing the default engine. The
adapter applies the case's native regular-file limit with `prlimit` before
Python starts. The engine-wide ceiling matches the runner's supported maximum;
stdout/stderr caps are enforced separately.

## Worker lifecycle and timing

The previous Resque multi-worker task did not forward termination to its actual
workers, leaving stale Redis registrations after container replacement. The new
supervisor owns and waits for every worker. A real regression check covers both
ordinary restarts and transitions between engines; each must report exactly the
configured worker count for ten consecutive samples. The health endpoint also
reports idle queues before their first job.

Queue timing is recorded only when enqueue and execution share a kernel boot ID,
which identifies the monotonic clock domain. No queue duration is derived across
different machines. Per-run logs distinguish runner queue wait, execution,
initialization, cleanup, persistence, callbacks, and app request duration.

The current engine and fresh-case grading behavior remain the defaults. No
latency or TLE percentage threshold has been introduced.


## Combined candidate

`--paired-combined` compares the unchanged Isolate baseline with go-judge in the
shared execution cgroup, HTTP connection reuse, and bounded dispatch. Set
`--dispatch-concurrency 4`. The callback outbox stays disabled in both variants.
Each profile gets a separate warm-up before every measured burst. Pair order
alternates across repetitions. Preparation and profile switching are excluded.

`--combined-ablation` adds go-judge alone as a third control and rotates the
three profiles across repetitions. This tests whether pooling and dispatch add
to the engine gain instead of assuming their individual percentages add up.
Generate baseline comparisons with `scripts/compare-runner-bench.py DIRECTORY
--candidate combined`. For the engine-only control, add
`--baseline go-judge-shared`; its report has a separate filename.

The combined matrix uses all three catalog workloads, concurrency 1, 10 and 25,
three repetitions, and 8 or 16 runner workers. Increasing workers keeps the
execution budget at 6 CPUs and 8 GiB. Run matrix entries sequentially; an
incomplete burst stops the sequence. Raw reports stay outside database volumes.


The first combined attempt reached 25 concurrent submissions but MySQL was
OOM-killed. Its inherited `/var/lib/mysql` tmpfs retained every earlier run's
rows and consumed the service's 1 GiB memory allowance. Docker OOM events and
per-burst cgroup samples are preserved under `combined-ransom-w8` and `resume`.
The benchmark override now uses the project-scoped `benchmark_mysql` disk
volume with the same CPU/memory/swap limits. Cleanup removes that volume.
The corrected matrix uses `combined-v2-*` labels; comparisons do not pool its
timings with the earlier RAM-backed database protocol. Final container states
are captured after each burst so service OOM failures remain inspectable.


A later disk-backed baseline burst completed all 850 cases correctly, but one
API result poll raised `RemoteProtocolError`. The old harness stopped observing
that submission; its final durable result was still passed. No container
restarted or was OOM-killed. The socket-close cause is unconfirmed. The v3
polling harness emits a transport-error event and count, waits the same 200 ms,
and continues idempotent result GETs until the original deadline. It never
retries a POST or execution. HTTP status errors still fail immediately. A
regression test covers both behaviors. Prior failed bursts remain excluded.
Completed v2 disk-backed 1/10 pairs had no transport errors and are retained.

To isolate pooling from bounded dispatch on go-judge, use `--paired-http
--engine go-judge-shared`. That experiment's baseline is go-judge with fresh
HTTP clients; only the candidate reuses them. The selected engine and both
profiles' configuration are recorded in its metadata and comparison JSON.


The completed Ransom Note three-way screen is in
[combined results](../benchmark-results/local-runner/combined-results/REPORT.md).
It contains three repetitions at each of 1, 10 and 25 concurrent submissions.
The full go-judge + pooling + dispatch-4 combination regressed at 25 in all
three pairs. It is excluded from the proposed performance combination. Pooling
without bounded dispatch was screened separately and selected for the wider matrix.
`--paired-combined --dispatch-concurrency 1` measures that smaller combination
against Isolate; setting 4 measures the full combination. Neither changes the
defaults. Host clock, temperature, CPU/I/O pressure and available thermal
throttle counters are sampled in subsequent runs. Earlier laptop runs did not
capture those diagnostics continuously, so thermal effects cannot be separated
precisely from their timing variation.


The completed selected matrix compared go-judge plus HTTP pooling with dispatch kept
sequential. Its [protocol and results](../benchmark-results/local-runner/selected-matrix/REPORT.md)
cover the three workloads, both runner-worker counts and all three concurrency
levels. All 108 measured bursts completed, and the JSON records
`matrix_complete: true`. A separate audit checks actual container limits,
worker counts, feature flags, disk-backed MySQL, service survival and complete
case results. Pooling-only screening against go-judge is retained separately
under `go-pooled-screen`; it improved the 10-submission pairs but had mixed
25-submission latency results.


A computer shutdown interrupted the first 16-worker Ransom Note burst at
concurrency 10. Completed pairs are retained; the partial pair is archived
and both variants rerun after restarting the disposable project. The recovered
database and container state are preserved under that entry's `interruption`
folder. New source/machine/Docker metadata is saved under `sessions`, with a
`resume-index.json` mapping. Ransom Note worker-count comparisons span boots
and are observational; the reboot and laptop clock variation prevent attributing
the entire difference to worker count. No pair combines opposite sides of the
shutdown. Dashboard identities must include the experiment and burst path,
since disposable database submission IDs can repeat after a reset.


## Completed combined comparison

The selected matrix completed 1,296 submissions and 44,496 measured case
results correctly. Warm-ups are separate. Go-judge plus HTTP pooling lowered
median API latency in all 12 loaded workload/worker cells and in 31 of 36
individual loaded pairs. Some pairs regressed; these are retained in the
report. At 25 submissions and 8 workers, median API latency fell by 11.6-15.1%
across the three workloads. This is a local diagnostic result, not an SLO.

Sixteen workers did not provide a consistent benefit under the fixed 6 CPU /
8 GiB limit. Number of Islands and Minimum Cost for Tickets were slower with
16 workers at every tested concurrency in their separate cohorts. Ransom Note
worker-count results span the shutdown and cannot isolate the worker effect.
Use 8 workers for this local budget while preserving 16 as a test profile.

Final checks passed: 121 backend tests, 25 integration/sandbox tests per engine
profile (the 50-submission test excluded), and Ruby adapter checks. Backend/test
Compose images built successfully. Ruff, Python compilation and shell syntax
checks passed. Ruff's existing Python 3.14 preview notice remains; no lint rules
were suppressed. Dedicated project containers, networks and test volumes are
removed after verification; reports and source snapshots remain on disk.

The application still defaults to Isolate, fresh HTTP clients and sequential
dispatch. The outbox, grouped jobs, persistent workers, and execution-engine
experiments remain opt-in. The ungrouped go-judge profile was slower than Judge0
on the A100 host. Compare the complete grouped-worker candidate against Judge0
before considering an engine change.

To recover another interrupted selected matrix, run
`python benchmark-results/local-runner/selected-matrix/run.py --candidate pooled`.
It retains complete entries and invokes `--resume` for partial ones. Resume
metadata stays separate from the original snapshot, and incomplete pairs are
archived before both sides rerun. Use a new label for a new source/profile
comparison rather than reusing old results.
