# Final equal-configuration engine check

This compares optimized Judge0/Isolate with the go-judge hybrid, changing the execution engine while retaining grouping, persistent Ruby workers, HTTP reuse and fresh Python state per case. Both use 16 runner workers, a 24 CPU ceiling, 8 GiB runner memory and four app workers. Defaults are unchanged.

Run this campaign by itself: it uses the existing disposable techniview-runner-bench Compose project. It must not overlap another runner benchmark. Verification creates its own disposable projects. Existing memory/swap guards and five-minute burst deadlines remain active.

The script verifies both profiles, then runs three pairs at 10 simultaneous submissions and six at 25, alternating engine order. It performs warm-ups separately. Each engine receives 180 measured Ransom Note submissions. These are repeated bursts, not sustained load. Per-burst p99 has few observations and must be read alongside p95 and maximum; this is not a production p99 guarantee. Allow roughly 45–90 minutes plus image builds, depending on host load and verifier duration. No overnight settings matrix is scheduled.

On the GPU, from a clean checkout of corniedj/infra-improvements:

```bash
cd ~/techniview-deploy
git fetch origin refs/heads/corniedj/infra-improvements
git merge --ff-only FETCH_HEAD
mkdir -p benchmark-results/local-runner
nohup bash scripts/run-final-engine-check.sh a100-equal-engines-v1 \
  > benchmark-results/local-runner/a100-equal-engines-v1-console.log 2>&1 < /dev/null &
```

Check status:

```bash
cat benchmark-results/local-runner/a100-equal-engines-v1/status.txt
tail -n 50 benchmark-results/local-runner/a100-equal-engines-v1-console.log
```

Detailed logs are in `a100-equal-engines-v1/verify-isolate.log`, `verify-go-judge.log`, `c10.log`, and `c25.log`. A failure stops the campaign and records a nonzero exit status. Use a new label for a fresh run; existing results are never overwritten. Do not rerun automatically after a failure.

When status is complete, package reports and raw evidence on the GPU:

```bash
cd ~/techniview-deploy/benchmark-results/local-runner
tar -czf ~/a100-equal-engines-v1-results.tar.gz \
  a100-equal-engines-v1 a100-equal-engines-v1-c10 a100-equal-engines-v1-c25
```

From the development PC:

```bash
scp corniedj@cs-gpu-00:~/a100-equal-engines-v1-results.tar.gz ~/a100-equal-engines-v1-results.tar.gz
```

Review REPORT.md and both comparison.json files for API tails, server completion, throughput and resource use. Check failure evidence before interpreting speed. Prefer retaining Judge0 if differences are small or inconsistent. This experiment does not implement a direct TechniView-to-go-judge migration.
