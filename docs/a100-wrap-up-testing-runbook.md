# A100 candidate recovery and worker scaling campaign

This follow-up keeps the candidate opt-in and tests two remaining questions:
whether a real go-judge worker restart during an executing grouped case is
handled without silently rerunning student code, and whether 16 workers improve
on 8 under the same execution resource budget.

Before timing, the driver runs the candidate integration, sandbox, and adapter
checks, then restarts the go-judge worker container during a long-running group
case. The restart check expects an explicit `runner_outcome_unknown` result,
completed group state, stable idempotency, and no automatic execution retry.
Only after these checks pass does it run the full paired matrix.

The matrix compares Judge0 and go-judge with grouped jobs, persistent bounded
Ruby workers, pooled HTTP, and fresh Python state per case. It runs Ransom Note,
Number of Islands, and Minimum Cost for Tickets at runner worker counts 8 and
16; each count uses concurrency 1, 10, and 25, with three paired repetitions.
Both sides of each pair use the same worker count. Runner CPU and memory limits
stay fixed at 6 CPUs and 8 GiB; app workers stay at 4. Each profile receives an
untimed warm-up. The existing host safety stops remain active.

## Update the GPU checkout

Run these commands on `cs-gpu-00`:

```bash
cd ~/techniview-deploy
git status --short --branch
git fetch origin refs/heads/corniedj/infra-improvements
git merge --ff-only FETCH_HEAD
```

## Start the campaign

The campaign takes roughly twice as long as the completed 8-worker-only run.
Start it detached so it can continue if the SSH connection closes:

```bash
cd ~/techniview-deploy
nohup python3 -u scripts/run-engine-comparison-matrix.py \
  --profile group-persistent --workers 8 16 \
  --label a100-readiness-v1 \
  > benchmark-results/local-runner/a100-readiness-v1-console.log 2>&1 \
  < /dev/null &
echo $! > benchmark-results/local-runner/a100-readiness-v1.pid
```

The restart verifier uses its own disposable Compose project and removes only
that project's containers, network, and database volume. The matrix uses the
usual dedicated benchmark project. Both preserve logs and results outside the
disposable database volume.

## Check progress

The campaign manifest is:

```bash
cat benchmark-results/local-runner/a100-readiness-v1-campaign/campaign.json
```

The campaign is complete when its top-level status is `complete`, verification
is `complete`, and all six workload/worker cells are `complete` with
`pair_count` 9. If `grep` is the only search tool installed, inspect those
fields with:

```bash
grep -n '"status"\|"workers"\|"pair_count"\|"verification_status"\|"updated_at"' \
  benchmark-results/local-runner/a100-readiness-v1-campaign/campaign.json
```

The worker restart evidence is saved at:

```text
benchmark-results/local-runner/go-judge-worker-restart-verification/restart-test.log
benchmark-results/local-runner/go-judge-worker-restart-verification/services.log
```

## Copy the compact results back

After the manifest says the campaign completed, run this on the GPU:

```bash
cd ~/techniview-deploy/benchmark-results/local-runner
tar -czf ~/a100-readiness-v1-results.tar.gz \
  a100-readiness-v1-campaign/REPORT.md \
  a100-readiness-v1-campaign/campaign.json \
  a100-readiness-v1-ransom-note-w8-try*/comparison.md \
  a100-readiness-v1-ransom-note-w8-try*/comparison.json \
  a100-readiness-v1-number-of-islands-w8-try*/comparison.md \
  a100-readiness-v1-number-of-islands-w8-try*/comparison.json \
  a100-readiness-v1-minimum-cost-for-tickets-w8-try*/comparison.md \
  a100-readiness-v1-minimum-cost-for-tickets-w8-try*/comparison.json \
  a100-readiness-v1-ransom-note-w16-try*/comparison.md \
  a100-readiness-v1-ransom-note-w16-try*/comparison.json \
  a100-readiness-v1-number-of-islands-w16-try*/comparison.md \
  a100-readiness-v1-number-of-islands-w16-try*/comparison.json \
  a100-readiness-v1-minimum-cost-for-tickets-w16-try*/comparison.md \
  a100-readiness-v1-minimum-cost-for-tickets-w16-try*/comparison.json \
  go-judge-worker-restart-verification/restart-test.log \
  go-judge-worker-restart-verification/services.log \
  verify-go-judge-group-persistent-services.log
```

Then copy it from a local terminal on the development PC:

```bash
scp corniedj@cs-gpu-00:~/a100-readiness-v1-results.tar.gz \
  ~/a100-readiness-v1-results.tar.gz
```

The campaign report records the source commit and links the six comparisons.
Each comparison includes API acceptance, API turnaround, server completion,
throughput, and stage summaries. Resource samples remain on the GPU host if a
stage needs deeper investigation. Small-sample p99 values are diagnostic, not
production guarantees.
