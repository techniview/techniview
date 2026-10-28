# A100 runner follow-up plan

## Goal

Decide whether to keep the grouped runner path, whether go-judge should replace
the current Judge0 path, and which service limits and worker counts fit the
available host. Keep changes behind test profiles until the engine and
reliability checks pass. Do not set a latency or TLE pass threshold from the
current small benchmark.

## Evidence already collected

The campaign `a100-group-persistent` completed all six cells on
`cs-gpu-00`, source commit `1f230c412a6a17d49b656dbd7132cfad11efc642`.
It ran Ransom Note, Number of Islands, and Minimum Cost for Tickets with 8 and
16 runner workers, at concurrency 1, 10, and 25, with three paired repetitions.
The runner budget stayed at 6 CPUs and 8 GiB. Four app workers were used.

The comparison was between the per-case path and a combined candidate that
groups cases into one runner job and reuses bounded Ruby workers. Both sides
used go-judge 1.13.3 and pooled app-to-runner HTTP connections. Each case still
ran in a fresh Python process. This is evidence for the combined runner change;
it does not isolate grouping from Ruby worker reuse, and it does not compare
Judge0 with go-judge.

Candidate API p50 improved by about 66–78% at concurrency 10 and 69–75% at
concurrency 25 across the six workload/worker cells. At concurrency 1, gains
were small or inconsistent. Moving from 8 to 16 workers did not show a
consistent benefit under the same 6-CPU limit.

The campaign tracker and compact comparisons were copied to
`~/campaign.json` and `~/a100-comparisons.tar.gz` on the development PC. The
full raw captures remain on `cs-gpu-00`. Preserve the archive and host captures
until the combined report is written.

## Test sequence

### 1. Consolidate and audit the A100 evidence

- Extract the six comparison JSON/Markdown pairs and campaign report into a
  named, durable results directory. Keep the original archive too.
- Confirm each cell has three complete pairs, no incomplete bursts, correct
  verdicts and case counts, and durable submission records.
- Summarize API acceptance and turnaround percentiles, server completion
  percentiles, errors, throughput, stage timings, resource use, and 8-vs-16
  worker differences. Mark p99 as diagnostic because each burst is small.
- Retrieve raw event and resource samples from the A100 only if the compact
  JSON cannot answer a specific question. Do not copy bulky captures by default.

The campaign tracker and compact reports from the completed grouped-worker run
are now stored under
`benchmark-results/local-runner/a100-group-persistent-imported/`. The `imported`
suffix keeps these copies separate from raw results produced on the GPU host.

**Decision:** Keep grouped jobs plus persistent Ruby workers as a promising
test candidate if correctness evidence is clean. The data so far does not
justify raising the worker count to 16 by default.

### 2. Engine-only Judge0 comparison (complete)

The engine-only comparison is complete. It used the existing API with
per-case execution, 8 runner workers, 4 app workers, and the same
6-CPU / 8-GiB execution budget. All 27 pairs across the three problems and
concurrency 1, 10, and 25 completed. The go-judge candidate was slower in every
pair, by 42–60% at concurrency 1, 28–117% at concurrency 10, and 58–80% at
concurrency 25. Queue-wait p50 roughly doubled in the stage aggregates.

See the [engine comparison findings](../benchmark-results/local-runner/a100-engine-ab-imported/FINDINGS.md)
and the [engine-only runbook](a100-engine-comparison-runbook.md).

**Decision:** Do not replace Judge0 with the ungrouped go-judge profile. The
separate grouped-worker campaign showed enough promise to test the combined
candidate directly against Judge0.

### 3. Compare the combined candidate with Judge0 (next)

The final paired profile compares current Judge0 against go-judge with grouped
submission jobs, persistent bounded Ruby workers, and pooled HTTP connections.
It keeps a fresh Python process per case. The test-only execution profile and
public API remain unchanged.

The campaign driver runs profile-specific integration, sandbox, and adapter
checks before timed runs. It then measures all three catalog problems at
concurrency 1, 10, and 25, with three paired repetitions, 8 runner workers,
4 app workers, and the same 6-CPU / 8-GiB execution budget. Results include API
acceptance, API turnaround, server completion, throughput, stage samples,
resource samples, and durable result state.

Use [`scripts/run-engine-comparison-matrix.py`](../scripts/run-engine-comparison-matrix.py)
with `--profile group-persistent`. The complete GPU instructions are in
[`a100-wrap-up-testing-runbook.md`](a100-wrap-up-testing-runbook.md).

**Decision:** Keep the current Judge0 default unless the combined candidate
passes correctness and shows a repeatable end-to-end improvement. This test
does not change the default automatically.

### 4. Find useful CPU and worker settings

Use the selected engine and one fixed execution model. Change one resource
dimension at a time. Keep memory at 8 GiB during the first CPU sweep, then test
memory only if resource samples show pressure or if the expected deployment
needs a different limit.

- CPU sweep: 6, 16, then 32 runner CPUs, with 8 runner workers and 4 app
  workers. Start with concurrency 25 on all three problems and three paired
  repetitions. Stop early if added CPU does not improve throughput or tail
  turnaround enough to justify its cost.
- Worker sweep: at the best CPU setting, compare 8 and 16 runner workers. Test
  32 only if the 16-worker run shows runner queueing rather than CPU
  saturation. Keep app workers at 4 for this comparison.
- App-worker sweep: change app workers only if dispatch delay or app queueing
  is a material part of the measured turnaround. Hold the chosen runner limits
  fixed.
- Record the actual cgroup limits and Docker configuration with every result;
  host CPU count alone does not describe the test allocation.

Do not run a large Cartesian product. Each comparison should answer whether
the bottleneck moved and whether more allocated capacity improved completed
submissions per second.

### 5. Run the 100-submission capacity check

After choosing the engine and resource settings, run one staged capacity test
at concurrency 25, then 50, then 100. Use all three catalog problems across
separate bursts. Keep the five-minute burst deadline, 200 ms polling, and
host-memory/swap guard. Record the same end-to-end and resource metrics.
Define any production latency or TLE targets before using the run as a release
gate; this plan does not invent those targets.

### 6. Review reliability before changing defaults

Run the failure and isolation checks against the chosen profile:

- Function-based and stdin/stdout problems.
- Globals, modified imports, files, background threads, and leftover child
  processes across cases.
- Wrong answers, ordinary exceptions, fatal exits, CPU/memory limits, and
  excessive output.
- Delayed, duplicate, rejected, and missing callbacks; app and runner restarts;
  requests whose execution outcome becomes unknown.
- Idempotency, partial results, grading progress, and durable results after
  restart.

Keep a fresh Python process per case. The shared-Python experiment leaked later
case input through a background thread and remains rejected.

**Decision:** Change defaults only after the engine comparison, correctness
review, failure checks, and capacity report agree. Otherwise keep the current
engine/default path and retain go-judge or grouped execution as an explicit
test profile.

## Run controls and artifacts

- Run one campaign at a time in its dedicated disposable Compose project.
- Keep the existing safety stop: stop load if available memory stays below
  2 GiB for five seconds or swap grows more than 512 MiB from the campaign
  start. Preserve completed reports and mark interrupted bursts incomplete.
- Build images and prepare accounts/problems before timing. Keep warm-ups,
  image builds, and preparation out of measured durations.
- Use a unique campaign label. Keep raw samples, compact JSON/Markdown reports,
  resource samples, source commit, machine/daemon versions, service limits, and
  worker counts outside disposable database volumes.
- Make the runner script resumable and sequential. On hosts without a user
  systemd bus, run it in a persistent terminal session or a logged background
  job and monitor `campaign.json`; do not restart a live campaign to check it.

