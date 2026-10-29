#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
label=${1:-a100-equal-engines-v1}
[[ "$label" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
root="benchmark-results/local-runner/$label"
mkdir -p "$root"
[[ ! -e "$root/status.txt" ]] || { echo 'Choose a new label; existing evidence is preserved.'; exit 2; }
trap 'rc=$?; if (( rc )); then echo "failed exit=$rc" > "$root/status.txt"; fi' EXIT
export RUNNER_EXEC_CPU_LIMIT=24 VERIFY_RUNNER_WORKERS=16
for engine in isolate go-judge; do
  echo "verifying $engine" > "$root/status.txt"
  bash scripts/verify-runner-candidate.sh "$engine-group-persistent" > "$root/verify-$engine.log" 2>&1
done
for spec in 10:3 25:6; do
  concurrency=${spec%:*}
  repetitions=${spec#*:}
  run_label="$label-c$concurrency"
  echo "running $run_label" > "$root/status.txt"
  python3 -u scripts/runner-bench.py --label "$run_label" \
    --paired-engine-group-persistent --optimized-baseline \
    --problem 'Ransom Note' --workers 16 --concurrency "$concurrency" \
    --repetitions "$repetitions" > "$root/c$concurrency.log" 2>&1
  python3 scripts/compare-runner-bench.py "benchmark-results/local-runner/$run_label" \
    --candidate go-judge-group-persistent
 done
python3 - "$label" <<'PY'
import json
import sys
from pathlib import Path
label = sys.argv[1]
root = Path('benchmark-results/local-runner')
lines = ['# Equal-configuration engine comparison', '',
         'Baseline: optimized Judge0/Isolate. Candidate: optimized go-judge hybrid.',
         'Both: grouping, persistent Ruby workers, pooled HTTP, fresh Python per case, 16 workers, 24 CPU quota.',
         'Repeated bursts, not sustained load. Percentiles below are per burst; p99 is diagnostic.', '',
         '| Burst | Engine | API p50 s | p95 s | p99 s | max s |',
         '|---|---|---:|---:|---:|---:|']
for c in (10, 25):
    report = json.loads((root / f'{label}-c{c}' / 'comparison.json').read_text())
    if report['incomplete_runs']:
        raise RuntimeError('Incomplete runs present')
    for pair in report['pairs']:
        metrics = pair['metrics']['api_submission_to_result_seconds']
        for variant in ('baseline', 'candidate'):
            values = ' | '.join(f'{metrics[p][variant]:.3f}' for p in ('p50', 'p95', 'p99', 'max'))
            lines.append(f"| {pair['pair']} | {variant} | {values} |")
(root / label / 'REPORT.md').write_text('\n'.join(lines) + '\n')
PY
echo complete > "$root/status.txt"
