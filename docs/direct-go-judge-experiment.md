# Direct go-judge experiment

This branch tests TechniView calling upstream go-judge directly. TechniView owns the submission queue, case attempts, expected outputs, verdicts, and recovery. The go-judge container owns only sandbox execution. The public submission API stays the same.

The direct mode is an experiment. A case attempt is committed before its HTTP request. If an app worker dies or the request outcome is ambiguous, TechniView records that case as unknown and never runs it again. Later cases continue after the worker lease expires. This favors avoiding duplicate student execution over retrying an uncertain attempt.

The standalone `direct` image target contains Python and go-judge, without the Judge0 Rails API, Redis, or runner PostgreSQL database. The Compose overlay disables those hybrid services. It uses a dedicated project, so cleanup touches only its own containers and test data.

Local verification uses:

```sh
COMPOSE_PROJECT_NAME=techniview-direct-check DIRECT_EXECUTION_SLOTS=4 DIRECT_WORKER_PROCESSES=1 RUNNER_CPU_LIMIT=6 \
  docker compose --env-file /dev/null -f compose.integration.yml -f compose.direct-experiment.yml \
  up -d --build --wait --scale app_worker=4 backend go-judge app_worker

COMPOSE_PROJECT_NAME=techniview-direct-check docker compose --env-file /dev/null \
  -f compose.integration.yml -f compose.direct-experiment.yml run --rm --no-deps tests \
  python -m pytest integration/test_direct_runner.py -q --override-ini=pythonpath=.

bash scripts/verify-direct-runner.sh

COMPOSE_PROJECT_NAME=techniview-direct-check docker compose --env-file /dev/null \
  -f compose.integration.yml -f compose.direct-experiment.yml down --volumes --remove-orphans
```

The focused API load check is `python -m performance.load_test` inside `tests`, with `LOAD_PROBLEM='Ransom Note'`, `LOAD_STUDENTS=10`, `LOAD_CONCURRENCY=10`, and `LOAD_JUDGE0_WORKERS` set to the execution slot count. Its report includes raw API samples and checks every persisted case. Use the same 200 ms result poll interval and the same CPU, memory, app, and execution slot limits for hybrid and direct runs. Warm both stacks, then collect three paired runs at 10 and 25 concurrent submissions. Preserve the full JSON output outside disposable Compose volumes. Include go-judge and app worker resource use in the comparison.

The existing A100 hybrid benchmark is the reference. A fresh paired run is still needed before deciding whether direct execution improves API p95/p99 enough to justify removing the Judge0 orchestration. Do not interpret a single-submission smoke test as a speed result.
