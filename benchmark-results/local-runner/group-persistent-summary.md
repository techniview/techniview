# Grouped jobs and persistent runner workers

This is a local comparison of the existing per-case path with grouped jobs and
persistent Ruby workers, using go-judge 1.13.3 and pooled app-to-runner HTTP
connections in both variants. Each submission still uses a fresh Python process
for each case. Timing is from submission POST start through terminal API result.

## Completed Ransom Note comparisons

| Runner workers | Concurrency | Complete pairs | Candidate p50 change across pairs | Result |
| ---: | ---: | ---: | ---: | --- |
| 8 | 1 | 3 | -19% to -28%, one +4% | Mixed, candidate faster twice |
| 8 | 10 | 3 | -38% to -70% | Candidate faster in all pairs |
| 8 | 25 | 3 | -45% to -70% | Candidate faster in all pairs |
| 16 | 1 | 3 | -1% to -30% | Candidate faster in all pairs |
| 16 | 10 | 3 | -51% to -72% | Candidate faster in all pairs |
| 16 | 25 | 0 | — | Stopped before a complete pair |

See the detailed [8-worker pairs](group-persistent-ransom-w8/comparison.md),
[16-worker pairs](group-persistent-ransom-w16/comparison.md), and raw samples in
those directories. Small-sample tail percentiles are diagnostic only. The
comparison combines grouping and persistent workers, so it does not measure
their separate contributions.

The 16-worker tests use the same 6-CPU / 8-GiB execution budget as the 8-worker
tests. Sixteen workers therefore oversubscribe the runner CPU allocation; they
do not receive 16 cores. Ransom Note c25 at 16 workers remains unmeasured.

The 8-worker stage samples show where the reduction came from. Across measured
bursts (stages are aggregated across concurrencies), per-case runner queue wait
had p50 6.79 s and p95 10.87 s in the baseline. Grouped-job queue wait had p50
0.020 s and p95 0.066 s. The candidate's per-case group execution duration had
p50 0.041 s and p95 0.096 s. App dispatch and API polling were each only a few
milliseconds at p50. Queueing was the main baseline cost; after grouping, the
remaining time is primarily execution and the end-to-end API path. See the raw
stage breakdown in the comparison JSON; stage totals combine concurrency cells
and should not be read as per-submission latency.

## Scope and stop

The plan's grouped-worker comparisons for Number of Islands and Minimum Cost for
Tickets were not run. At 16 workers, the c25 Ransom Note baseline was stopped
incomplete after campaign-wide swap growth exceeded 512 MiB from the campaign
start. The current host had 10.0 GiB available memory at stop, but swap in use
had increased by about 898 MiB from its 1,958-MiB starting level. The partial
burst has exit code 137 and is excluded. The dedicated Compose project and its
disposable database volume were removed; benchmark reports remain on disk.

The [campaign stop record](group-persistent-ransom-w16/campaign-safety-stop.json)
contains the exact counters. No more load was started after the stop. A future
campaign needs a recovered host and a new label.

## Other execution model

The experimental shared-Python profile did not preserve fresh-case isolation:
a background thread could read a later case's input. It remains test-only and
is not a candidate for the default grading path. The current engine and public
submission API remain unchanged.
