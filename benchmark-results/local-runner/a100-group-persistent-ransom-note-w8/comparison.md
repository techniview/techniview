# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.426 | 4.991 | -0.435 | -8.0% |
| c1-r2 | 4.968 | 4.934 | -0.034 | -0.7% |
| c1-r3 | 5.386 | 4.964 | -0.422 | -7.8% |
| c10-r1 | 33.038 | 6.332 | -26.705 | -80.8% |
| c10-r2 | 29.389 | 7.538 | -21.852 | -74.4% |
| c10-r3 | 30.958 | 7.554 | -23.404 | -75.6% |
| c25-r1 | 58.555 | 15.087 | -43.467 | -74.2% |
| c25-r2 | 60.106 | 17.672 | -42.434 | -70.6% |
| c25-r3 | 58.546 | 15.001 | -43.545 | -74.4% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
