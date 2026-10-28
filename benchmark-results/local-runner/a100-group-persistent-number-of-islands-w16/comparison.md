# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.656 | 5.372 | -0.284 | -5.0% |
| c1-r2 | 5.187 | 4.945 | -0.243 | -4.7% |
| c1-r3 | 5.651 | 3.715 | -1.936 | -34.3% |
| c10-r1 | 38.599 | 8.268 | -30.331 | -78.6% |
| c10-r2 | 35.631 | 8.732 | -26.899 | -75.5% |
| c10-r3 | 37.640 | 7.581 | -30.058 | -79.9% |
| c25-r1 | 61.637 | 17.630 | -44.007 | -71.4% |
| c25-r2 | 63.960 | 16.572 | -47.389 | -74.1% |
| c25-r3 | 62.946 | 13.718 | -49.228 | -78.2% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
