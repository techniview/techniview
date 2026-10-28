# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.677 | 5.383 | -0.295 | -5.2% |
| c1-r2 | 5.636 | 4.533 | -1.103 | -19.6% |
| c1-r3 | 5.657 | 5.610 | -0.048 | -0.8% |
| c10-r1 | 31.165 | 9.412 | -21.754 | -69.8% |
| c10-r2 | 31.081 | 7.771 | -23.310 | -75.0% |
| c10-r3 | 39.241 | 7.453 | -31.788 | -81.0% |
| c25-r1 | 65.832 | 16.612 | -49.221 | -74.8% |
| c25-r2 | 70.919 | 17.680 | -53.238 | -75.1% |
| c25-r3 | 70.328 | 17.607 | -52.721 | -75.0% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
