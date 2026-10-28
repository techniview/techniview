# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.408 | 3.917 | -1.491 | -27.6% |
| c1-r2 | 5.202 | 5.615 | +0.413 | +7.9% |
| c1-r3 | 5.176 | 5.178 | +0.002 | +0.0% |
| c10-r1 | 32.475 | 7.419 | -25.056 | -77.2% |
| c10-r2 | 28.211 | 9.146 | -19.065 | -67.6% |
| c10-r3 | 30.557 | 10.283 | -20.274 | -66.3% |
| c25-r1 | 66.469 | 20.880 | -45.589 | -68.6% |
| c25-r2 | 61.924 | 16.230 | -45.694 | -73.8% |
| c25-r3 | 63.090 | 19.542 | -43.548 | -69.0% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
