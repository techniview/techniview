# Local go-judge comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.637 | 9.027 | +3.391 | +60.2% |
| c1-r2 | 5.623 | 8.814 | +3.191 | +56.8% |
| c1-r3 | 5.853 | 9.002 | +3.149 | +53.8% |
| c10-r1 | 30.594 | 66.465 | +35.871 | +117.2% |
| c10-r2 | 35.162 | 51.933 | +16.771 | +47.7% |
| c10-r3 | 34.963 | 59.418 | +24.455 | +69.9% |
| c25-r1 | 66.937 | 116.832 | +49.895 | +74.5% |
| c25-r2 | 70.057 | 110.549 | +40.492 | +57.8% |
| c25-r3 | 66.970 | 111.016 | +44.045 | +65.8% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
