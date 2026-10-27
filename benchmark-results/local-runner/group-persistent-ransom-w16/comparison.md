# Local group-persistent comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.859 | 5.831 | -0.029 | -0.5% |
| c1-r2 | 4.540 | 3.386 | -1.154 | -25.4% |
| c1-r3 | 4.505 | 3.175 | -1.330 | -29.5% |
| c10-r1 | 26.972 | 7.648 | -19.324 | -71.6% |
| c10-r2 | 24.904 | 7.257 | -17.646 | -70.9% |
| c10-r3 | 32.023 | 15.850 | -16.173 | -50.5% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.

Incomplete runs excluded: c25-r1-baseline.
Further load stopped under the specified resource safety policy.
