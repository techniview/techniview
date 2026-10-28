# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.416 | 3.932 | -1.484 | -27.4% |
| c1-r2 | 6.034 | 5.394 | -0.640 | -10.6% |
| c1-r3 | 5.645 | 6.281 | +0.636 | +11.3% |
| c10-r1 | 29.899 | 7.098 | -22.801 | -76.3% |
| c10-r2 | 31.304 | 8.948 | -22.357 | -71.4% |
| c10-r3 | 30.383 | 7.096 | -23.287 | -76.6% |
| c25-r1 | 61.248 | 16.538 | -44.710 | -73.0% |
| c25-r2 | 60.327 | 15.469 | -44.858 | -74.4% |
| c25-r3 | 60.441 | 19.962 | -40.479 | -67.0% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
