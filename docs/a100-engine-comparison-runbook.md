# Run the A100 Judge0 versus go-judge comparison

The campaign runner compares the existing Judge0 integration with the
go-judge test profile through the TechniView submission API. It holds the
execution budget at 6 CPUs and 8 GiB, uses 8 runner workers and 4 app workers,
and runs all three catalog problems at concurrency 1, 10, and 25 with three
paired repetitions. Case grouping, persistent Ruby workers, and HTTP
connection reuse are disabled on both sides so this run tests the engine
change by itself. Each case keeps a fresh Python process.

The runner builds images before timing, runs one workload at a time, records a
campaign manifest, checks the existing host memory/swap stop limits, and
resumes an interrupted workload under a new attempt label. It leaves reports
outside Compose volumes. The existing benchmark runner removes only the
`techniview-runner-bench` project and its disposable test volume after each
workload.

## Prepare the GPU checkout

In the existing `cs-gpu-00` checkout, first confirm it is clean and on the
experiment branch:

```bash
cd ~/techniview-deploy
git status --short --branch
```

After the follow-up changes are pushed, fast-forward the branch:

```bash
git fetch origin refs/heads/corniedj/infra-improvements
git merge --ff-only FETCH_HEAD
```

The runner requires Docker Compose and the branch's benchmark source. It will
build the Judge0 and go-judge images itself. Image builds are outside timed
bursts. No production environment file or credential is used.

## Start the campaign

Run it detached so an SSH disconnect does not stop the process:

```bash
cd ~/techniview-deploy
nohup python3 -u scripts/run-engine-comparison-matrix.py --label a100-engine-ab \
  > benchmark-results/local-runner/a100-engine-ab-console.log 2>&1 < /dev/null &
echo $! > benchmark-results/local-runner/a100-engine-ab.pid
```

The script uses a unique campaign label. If that campaign already exists, it
refuses to overwrite it. Choose a new label for a separate campaign.

## Check progress

The campaign manifest updates as images build and each workload starts and
finishes:

```bash
cat benchmark-results/local-runner/a100-engine-ab-campaign/campaign.json
```

Follow the live log when useful:

```bash
tail -f benchmark-results/local-runner/a100-engine-ab-console.log
```

Or check the process without attaching to it:

```bash
ps -p "$(cat benchmark-results/local-runner/a100-engine-ab.pid)" -o pid,etime,stat,cmd
```

The runner stops if host available memory remains below 2 GiB for five seconds
or swap grows more than 512 MiB from the campaign start. A safety-stopped
campaign must not resume on the same boot. After a reboot and host recovery,
resume it with:

```bash
python3 -u scripts/run-engine-comparison-matrix.py --label a100-engine-ab --resume
```

For an ordinary interruption, the same resume command skips complete workloads
and starts an incomplete one under a new attempt label. Partial samples remain
on disk and are not mixed into completed comparisons.

## Collect the compact results

When `campaign.json` says `"status": "complete"`, package only the campaign
manifest and comparison summaries. This avoids copying raw captures and service
logs:

```bash
cd ~/techniview-deploy/benchmark-results/local-runner
tar -czf ~/a100-engine-ab-results.tar.gz \
  a100-engine-ab-campaign/REPORT.md \
  a100-engine-ab-campaign/campaign.json \
  a100-engine-ab-ransom-note-try*/comparison.md \
  a100-engine-ab-ransom-note-try*/comparison.json \
  a100-engine-ab-number-of-islands-try*/comparison.md \
  a100-engine-ab-number-of-islands-try*/comparison.json \
  a100-engine-ab-minimum-cost-for-tickets-try*/comparison.md \
  a100-engine-ab-minimum-cost-for-tickets-try*/comparison.json
```

From a local terminal on the development PC, copy it with:

```bash
scp corniedj@cs-gpu-00:~/a100-engine-ab-results.tar.gz ~/a100-engine-ab-results.tar.gz
```

The comparison must contain nine complete pairs per workload. Read the
comparison JSON for API acceptance, result turnaround, server completion,
throughput, and stage measurements. Treat p99 as diagnostic for these sample
sizes. The raw captures remain on the GPU host for follow-up analysis.
