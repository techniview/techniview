# Local go-judge comparison

Times run from request start to completed results received through the API.
Negative changes mean lower latency. Paired results exclude warm-ups.

| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| c1-r1 | 5.392 | 8.538 | +3.147 | +58.4% |
| c1-r2 | 5.399 | 8.574 | +3.175 | +58.8% |
| c1-r3 | 5.813 | 8.571 | +2.758 | +47.4% |
| c10-r1 | 29.827 | 56.546 | +26.719 | +89.6% |
| c10-r2 | 29.023 | 62.551 | +33.528 | +115.5% |
| c10-r3 | 36.697 | 47.087 | +10.390 | +28.3% |
| c25-r1 | 63.809 | 114.982 | +51.173 | +80.2% |
| c25-r2 | 63.950 | 108.757 | +44.807 | +70.1% |
| c25-r3 | 69.061 | 109.067 | +40.006 | +57.9% |

Small-sample p99 values are diagnostic, not production guarantees.

See the companion JSON for acceptance, server completion, and API tails.
Stage aggregates include both variants and warm-ups. They cannot attribute changes to one variant.
The public submission API and grading behavior are unchanged.
