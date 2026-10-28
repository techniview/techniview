# A100-host Judge0 versus go-judge findings

## Result

The campaign completed on `cs-gpu-00` from source commit
`c0ae1d00c7663f3a54cd4b4da517f7d670bc9260`. It ran all three catalog
problems, with 8 runner workers and 4 app workers under the fixed 6-CPU / 8-GiB
execution budget. Each workload had nine complete pairs: three repetitions at
concurrency 1, 10, and 25. The paired-engine profile kept case grouping,
persistent Ruby workers, and HTTP reuse disabled. Each case used a fresh
Python process. The host reports an AMD EPYC 7742 with 64 cores and 128
hardware threads. The benchmark runs on the host CPU; it does not use the A100
GPU.

Every paired run favored Judge0 for API p50. Values below are the median of
the three paired repetitions for each workload and concurrency.

| Workload | Concurrency 1, Judge0 -> go-judge | Concurrency 10, Judge0 -> go-judge | Concurrency 25, Judge0 -> go-judge |
| --- | ---: | ---: | ---: |
| Ransom Note | 5.40 -> 8.57 s (+58%) | 29.83 -> 56.55 s (+90%) | 63.95 -> 109.07 s (+70%) |
| Number of Islands | 5.84 -> 8.61 s (+48%) | 30.82 -> 50.77 s (+65%) | 65.80 -> 109.18 s (+66%) |
| Minimum Cost for Tickets | 5.64 -> 9.00 s (+57%) | 34.96 -> 59.42 s (+70%) | 66.97 -> 111.02 s (+66%) |

Across individual pairs, go-judge was 42–60% slower at concurrency 1,
28–117% slower at concurrency 10, and 58–80% slower at concurrency 25.
These tail ranges reflect nine pairs per workload and are diagnostic, not
production guarantees.

Server completion p50 tracked API-observed p50 closely in both profiles. The
extra time is therefore in execution/queueing, not waiting for the client to
retrieve completed results.

## Where the time went

The stage aggregates combine all three concurrency levels and exclude warm-up
bursts. They are event-level summaries, not per-submission decomposition.

- Runner queue-wait p50 was about 18–19 seconds with Judge0 and 38–40 seconds
  with go-judge. The corresponding p95 values were about 25–27 and 51–53
  seconds.
- App dispatch p50 stayed near 17–18 milliseconds for both profiles.
- go-judge requests had p50 around 72–78 milliseconds and p95 around
  135–147 milliseconds.
- Callback delivery p50 was about 58–61 milliseconds with Judge0 and
  107–108 milliseconds with go-judge. That difference is measurable but is
  small beside the queue-wait increase.

Queueing is the clearest measured bottleneck in this comparison. The compact
archive does not include resource sample streams, so it does not establish
whether CPU throttling, worker scheduling, or runner integration caused the
larger queue. Those raw samples remain on `cs-gpu-00`.

## Recommendation

Do not replace the current Judge0 path with the ungrouped go-judge profile from
this run. It was slower at every workload and concurrency.

This does not rule out go-judge with grouped jobs and persistent Ruby workers.
The separate A100 grouped-worker campaign found large gains over its own
per-case go-judge path at concurrency 10 and 25. That result did not compare
the combined go-judge candidate directly with Judge0. The next useful engine
test is a paired full-API comparison of current Judge0 against grouped,
persistent go-judge, while keeping fresh Python state per case and holding
resource limits constant.

The present evidence does not justify increasing worker counts or changing
resource environment values. Keep 8 workers for the next paired comparison;
the earlier 8-versus-16 grouped-worker runs showed no consistent advantage
for 16 under the same CPU budget.

## Files

- [`campaign/REPORT.md`](campaign/REPORT.md) and [`campaign/campaign.json`](campaign/campaign.json)
- [Ransom Note comparison](a100-engine-ab-ransom-note-try01/comparison.md)
- [Number of Islands comparison](a100-engine-ab-number-of-islands-try01/comparison.md)
- [Minimum Cost for Tickets comparison](a100-engine-ab-minimum-cost-for-tickets-try01/comparison.md)
- [`original-compact-results.tar.gz`](original-compact-results.tar.gz)

