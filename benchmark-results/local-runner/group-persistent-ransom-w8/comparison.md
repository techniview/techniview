# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 3.492 | 3.628 | +0.135 | +3.9% |
| c1-r2 | 3.689 | 2.976 | -0.713 | -19.3% |
| c1-r3 | 3.932 | 2.815 | -1.118 | -28.4% |
| c10-r1 | 20.028 | 6.065 | -13.963 | -69.7% |
| c10-r2 | 20.438 | 6.832 | -13.606 | -66.6% |
| c10-r3 | 20.926 | 12.898 | -8.028 | -38.4% |
| c25-r1 | 51.885 | 22.573 | -29.312 | -56.5% |
| c25-r2 | 49.621 | 27.545 | -22.076 | -44.5% |
| c25-r3 | 52.145 | 15.707 | -36.438 | -69.9% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
