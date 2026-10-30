# Runner decision and evidence

Production uses standalone go-judge 1.13.3 with Python 3.14.8. The application
owns durable submission and case attempts in MySQL, grades the returned output,
and marks interrupted attempts as unknown. go-judge owns sandbox execution only.

The earlier Judge0 fork, grouped Ruby workers, PostgreSQL, and Redis were part of
the hybrid experiment. They are no longer built or deployed. The A100 comparison
and local direct integration tests informed this migration; historical hybrid
figures are preserved in benchmark artifacts. The direct path has passed the
real sandbox and application integration suite, including CPU, memory, output,
filesystem isolation, result persistence, and worker restart recovery. A hosted
100-concurrent submission capacity result is still needed before making a campus
throughput claim.
