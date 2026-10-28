# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.455 | 5.210 | -0.245 | -4.5% |
| c1-r2 | 5.648 | 5.142 | -0.505 | -8.9% |
| c1-r3 | 5.412 | 5.620 | +0.207 | +3.8% |
| c10-r1 | 28.795 | 7.812 | -20.984 | -72.9% |
| c10-r2 | 38.174 | 6.812 | -31.362 | -82.2% |
| c10-r3 | 29.786 | 8.272 | -21.514 | -72.2% |
| c25-r1 | 69.507 | 16.472 | -53.034 | -76.3% |
| c25-r2 | 64.068 | 17.992 | -46.076 | -71.9% |
| c25-r3 | 66.184 | 13.986 | -52.199 | -78.9% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
