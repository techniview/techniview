# Final A100 CPU and worker capacity comparison

This is the final planned runner-capacity campaign. It compares the current
Judge0 path with go-judge using grouped submissions, persistent bounded Ruby
workers, pooled HTTP, and fresh Python state for every case.

The matrix tests runner CPU quotas of 6 and 24, each with 8, 16, and 24 runner
workers. It runs Ransom Note, Number of Islands, and Minimum Cost for Tickets
at concurrency 1, 10, and 25, with three paired repetitions. Both sides of each
pair use the same worker count and CPU quota. Runner memory remains 8 GiB, app
workers remain at 4, and other service limits stay fixed. Each profile gets an
untimed warm-up. The campaign writes compact worker CPU, throttling, memory, and
OOM summaries into the comparison JSON and Markdown.

Before timed runs, it runs the candidate integration and sandbox checks, then
restarts the go-judge worker service during an active grouped case. The recovery
check expects an explicit unknown-outcome result, completed group state, stable
idempotency, and no automatic re-execution. A campaign with all settings has 18
cells and 9 pairs per cell. At the observed pace, allow about 6 to 9 hours.

## Update the GPU checkout

Run these commands on `cs-gpu-00`:

```bash
cd ~/techniview-deploy
git status --short --branch
git fetch origin refs/heads/corniedj/infra-improvements
git merge --ff-only FETCH_HEAD
```

## Start the final campaign

Start it detached so it can continue if the SSH connection closes:

```bash
cd ~/techniview-deploy
nohup python3 -u scripts/run-engine-comparison-matrix.py \
  --profile group-persistent \
  --cpu-limits 6 24 \
  --workers 8 16 24 \
  --label a100-final-capacity-v1 \
  > benchmark-results/local-runner/a100-final-capacity-v1-console.log 2>&1 \
  < /dev/null &
echo $! > benchmark-results/local-runner/a100-final-capacity-v1.pid
```

The benchmark driver runs one cell at a time and keeps its host safety stops
active. It stops if available memory stays below 2 GiB for five seconds or swap
grows by more than 512 MiB from the campaign start. The isolated verifier and
benchmark Compose projects remove only their own containers, networks, and
database volumes. Reports and resource samples are kept outside those volumes.

## Check progress

The campaign manifest is:

```bash
cat benchmark-results/local-runner/a100-final-capacity-v1-campaign/campaign.json
```

The run is complete when the top-level status and verification status are both
`complete`, and all 18 cells show `complete` with `pair_count` 9. To inspect the
key fields with `grep`:

```bash
grep -n '"status"\|"cpu_limit"\|"workers"\|"pair_count"\|"verification_status"\|"updated_at"' \
  benchmark-results/local-runner/a100-final-capacity-v1-campaign/campaign.json
```

Follow the console log if needed:

```bash
tail -f benchmark-results/local-runner/a100-final-capacity-v1-console.log
```

The intentional restart evidence is saved at:

```text
benchmark-results/local-runner/go-judge-worker-restart-verification/restart-test.log
benchmark-results/local-runner/go-judge-worker-restart-verification/services.log
```

## Copy the results back

After the campaign completes, package its report, all comparisons, and restart
verification logs on the GPU:

```bash
cd ~/techniview-deploy/benchmark-results/local-runner
tar -czf ~/a100-final-capacity-v1-results.tar.gz \
  a100-final-capacity-v1-campaign/REPORT.md \
  a100-final-capacity-v1-campaign/campaign.json \
  a100-final-capacity-v1-*-cpu*-w*-try*/comparison.md \
  a100-final-capacity-v1-*-cpu*-w*-try*/comparison.json \
  go-judge-worker-restart-verification/restart-test.log \
  go-judge-worker-restart-verification/services.log \
  verify-go-judge-group-persistent-services.log
```

Then copy the archive from a local terminal on the development PC:

```bash
scp corniedj@cs-gpu-00:~/a100-final-capacity-v1-results.tar.gz \
  ~/a100-final-capacity-v1-results.tar.gz
```

The paired reports show API latency and throughput. Their resource section
shows median worker CPU cores used, the fraction of CPU periods that were
throttled, peak sampled worker memory, and OOM events. Small-sample p99 values
remain diagnostic, not production guarantees.
