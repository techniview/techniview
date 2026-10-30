#!/usr/bin/env bash
set -euo pipefail
[[ -f /sys/fs/cgroup/cgroup.controllers ]] || { echo 'Runner requires cgroup v2' >&2; exit 1; }
grep -qx '0::/' /proc/self/cgroup || { echo 'Runner requires a private cgroup namespace' >&2; exit 1; }
export FORK_PER_JOB=false
export GO_JUDGE_URL=http://127.0.0.1:5050
# Both processes share this container's execution budget; Go owns sandbox cgroups.
setsid /usr/local/bin/go-judge -http-addr 127.0.0.1:5050 -no-fallback \
  -mount-conf /etc/go-judge-mount.yaml -parallelism "${COUNT:-16}" \
  -output-limit "${MAX_MAX_FILE_SIZE:-4096}k" -copy-out-limit "${MAX_MAX_FILE_SIZE:-4096}k" -src-prefix /opt/python &
go_pid=$!
ruby_pid=
cleanup() {
  status=$?; trap - EXIT TERM INT
  kill -TERM -- "-$go_pid" 2>/dev/null || true
  if [[ -n "$ruby_pid" ]]; then kill -TERM "$ruby_pid" 2>/dev/null || true; fi
  wait || true
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
for attempt in $(seq 1 100); do
  if /opt/python/bin/python3.14 -c 'import urllib.request; urllib.request.urlopen("http://localhost:5050/version", timeout=1).read()' 2>/dev/null; then break; fi
  kill -0 "$go_pid"
  [[ "$attempt" != 100 ]] || exit 1
  sleep 0.1
done
export HOME=/home/judge0
setsid setpriv --reuid=judge0 --regid=judge0 --init-groups /api/docker-entrypoint.sh "$@" &
ruby_pid=$!
# Fail the service when either component exits, rather than advertise unused workers.
wait -n "$go_pid" "$ruby_pid"
exit 1
