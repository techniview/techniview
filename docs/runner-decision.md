# Runner decision

The selected execution engine is go-judge 1.13.3. Retain the existing durable runner orchestration for this implementation, with grouped submission jobs, persistent Ruby workers, connection pooling and fresh Python/sandbox state for every case.

The experiment branch `corniedj/infra-improvements` preserves the experiments. The equal-settings A100-host campaign ran from commit `78528f2c13078e8e6096350dc29b33be840231f1`. Both engines had 16 runner workers, a 24 CPU ceiling, 8 GiB memory, grouping, persistent workers and pooled HTTP. At 10 concurrent submissions, medians of burst API p95 were 15.287 seconds for Isolate and 10.106 for go-judge. At 25, they were 28.736 and 21.368 seconds. Go-judge improved the slowest completion in all nine pairs. Each engine completed 180 Ransom Note submissions and 6,120 case results. Both verification suites reported 26 passed, three skipped and one deselected. The sample is diagnostic and does not establish a production p99 guarantee.

This clean branch starts from main at `14fc7da` and ports the chosen implementation. It excludes shared Python execution, callback-outbox experiments, bounded parallel dispatch experiments, and load-matrix scaffolding. Existing application and runner database migrations are retained; the grouped-runner migration adds its own tables. No live installation or old queue contents are assumed. Use fresh disposable databases when validating this branch.

The private runner API and app submission API remain compatible where useful, but the worker image only executes through go-judge. The extra orchestration is deliberate: replacing it would require rebuilding durable attempt handling, progress, recovery and idempotency. That rewrite has no measured benefit and is deferred.

Raw campaign evidence remains in the original checkout under `benchmark-results/local-runner/a100-equal-engines-v1-imported/` and in the copied archive. It is not included in this implementation branch.

The clean port enables go-judge's strictMemoryLimit per command. Verification found that default memory monitoring could report an excess only after a short program had already completed. The strict setting enforces the sandbox memory ceiling during execution. This is a correctness fix beyond the benchmark configuration, so the historical performance numbers are evidence for the architecture rather than exact predictions for this build.

## Clean-port verification

Local verification passed 109 backend unit tests; 26 integration/sandbox tests with the host-controlled restart test skipped and the 50-submission load test deselected; the separate worker restart recovery test; adapter result/unknown-outcome checks; runner image size, Ruby syntax and runtime-library checks; and the frontend build. Compose configurations validate for local, integration and deployment layouts. Integration used four runner workers under a 6 CPU / 4 GiB local limit, not the A100 capacity setting. No new latency benchmark was run for this port.
