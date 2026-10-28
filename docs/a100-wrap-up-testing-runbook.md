# Final grouped go-judge comparison on the A100 host

This campaign compares the current Judge0 path with the strongest test
candidate from the prior runs: go-judge with grouped submission jobs,
persistent bounded Ruby workers, and pooled app-to-runner connections. Python
still starts fresh for every case. The candidate remains test-only.

Before timing, the campaign runs the grouped-profile integration, sandbox, and
go-judge adapter checks. It then compares all three canonical workloads at
concurrency 1, 10, and 25, with three paired repetitions per workload. Both
profiles use 8 runner workers, 4 app workers, and a 6-CPU / 8-GiB execution
budget. Paired order alternates. Each profile gets its own untimed warm-up.

The campaign does not test a 100-submission burst or larger resource limits.
It also does not inject an engine crash during a live grouped submission.
Those capacity and crash-recovery checks remain separate work after this
candidate is reviewed.

## Update the GPU checkout

Run these commands on `cs-gpu-00` from the existing branch checkout:

```bash
cd ~/techniview-deploy
git status --short --branch
git fetch origin refs/heads/corniedj/infra-improvements
git merge --ff-only FETCH_HEAD
```

The imported A100 reports live under a separate `a100-group-persistent-imported`
directory. The new campaign uses its own label, so it will not replace those
files or the earlier raw campaign output.

## Run the final comparison

Start it detached so it survives an SSH disconnect:

```bash
cd ~/techniview-deploy
nohup python3 -u scripts/run-engine-comparison-matrix.py \
  --profile group-persistent --label a100-final-group-persistent \
  > benchmark-results/local-runner/a100-final-group-persistent-console.log 2>&1 \
  < /dev/null &
echo $! > benchmark-results/local-runner/a100-final-group-persistent.pid
```

The script builds images outside the timed bursts, uses one workload at a time,
and stops on the existing host safety limits: available memory below 2 GiB for
five seconds, or swap growth over 512 MiB from the campaign start. It records
campaign state and preserves incomplete attempts. An ordinary interrupted
workload can be retried with the same label. A safety-stopped campaign cannot
resume on the same boot.

## Monitor it

Read the campaign manifest:

```bash
cat benchmark-results/local-runner/a100-final-group-persistent-campaign/campaign.json
```

Follow the log if you want live output:

```bash
tail -f benchmark-results/local-runner/a100-final-group-persistent-console.log
```

The manifest records the profile verification result, image build, and the
status of each workload. A successful run ends with `"status": "complete"`.
Each workload must have nine complete pairs and no incomplete runs.

For an ordinary interruption, resume with:

```bash
python3 -u scripts/run-engine-comparison-matrix.py \
  --profile group-persistent --label a100-final-group-persistent --resume
```

After a safety stop, wait for host recovery and reboot before resuming. The
driver establishes a new swap baseline after the boot changes.

## Copy compact results back

Once the campaign is complete, run this in the GPU SSH session:

```bash
cd ~/techniview-deploy/benchmark-results/local-runner
tar -czf ~/a100-final-group-persistent-results.tar.gz \
  a100-final-group-persistent-campaign/REPORT.md \
  a100-final-group-persistent-campaign/campaign.json \
  a100-final-group-persistent-ransom-note-try*/comparison.md \
  a100-final-group-persistent-ransom-note-try*/comparison.json \
  a100-final-group-persistent-number-of-islands-try*/comparison.md \
  a100-final-group-persistent-number-of-islands-try*/comparison.json \
  a100-final-group-persistent-minimum-cost-for-tickets-try*/comparison.md \
  a100-final-group-persistent-minimum-cost-for-tickets-try*/comparison.json
```

Then, in a local terminal on the development PC:

```bash
scp corniedj@cs-gpu-00:~/a100-final-group-persistent-results.tar.gz \
  ~/a100-final-group-persistent-results.tar.gz
```

The campaign report contains the source commit and workload links. Comparison
JSON includes API acceptance, API turnaround, server completion, throughput,
and stage summaries. Raw resource samples, service logs, and durable database
snapshots remain on the GPU host if a slower stage needs investigation.

