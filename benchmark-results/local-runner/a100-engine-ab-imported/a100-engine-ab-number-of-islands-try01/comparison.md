# Local go-judge comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.626 | 8.608 | +2.982 | +53.0% |
| c1-r2 | 6.056 | 8.603 | +2.547 | +42.1% |
| c1-r3 | 5.838 | 8.616 | +2.778 | +47.6% |
| c10-r1 | 30.820 | 50.766 | +19.946 | +64.7% |
| c10-r2 | 35.979 | 51.996 | +16.017 | +44.5% |
| c10-r3 | 30.391 | 50.012 | +19.621 | +64.6% |
| c25-r1 | 65.803 | 110.013 | +44.209 | +67.2% |
| c25-r2 | 66.392 | 109.183 | +42.791 | +64.5% |
| c25-r3 | 65.712 | 108.920 | +43.209 | +65.8% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
