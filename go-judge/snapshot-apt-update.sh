#!/bin/sh
set -eu

attempts=6
backoff=30
log=/tmp/snapshot-apt.log
patterns='Failed to fetch|Some index files failed|Connection failed|Gateway Timeout|TooManyRequests|No healthy backends|Hash Sum mismatch|Segmentation fault|Killed'

run_update() {
    set +e
    apt-get update >"$log" 2>&1
    rc=$?
    set -e
    if [ "$rc" -eq 0 ] && ! grep -Eq "$patterns" "$log"; then
        tail -n 50 "$log"
        return 0
    fi
    grep -E "$patterns" "$log" | tail -n 20 >&2 || true
    return 1
}

run_install() {
    set +e
    apt-get install -y --no-install-recommends "$@" >"$log" 2>&1
    rc=$?
    set -e
    if [ "$rc" -eq 0 ] && ! grep -Eq "$patterns" "$log"; then
        tail -n 50 "$log"
        return 0
    fi
    grep -E "$patterns" "$log" | tail -n 20 >&2 || true
    return 1
}

retry() {
    attempt=1
    until "$@"; do
        if [ "$attempt" -ge "$attempts" ]; then
            printf 'snapshot.debian.org sources still failing after %s attempts\n' "$attempts" >&2
            exit 1
        fi
        printf '%s: attempt %s failed, retrying in %ss\n' "$1" "$attempt" "$backoff" >&2
        sleep "$backoff"
        backoff=$((backoff * 2))
        attempt=$((attempt + 1))
    done
}

rm -f /etc/apt/sources.list.d/debian.sources
retry run_update
if [ "${1:-}" = "install" ]; then
    shift
fi
if [ "$#" -gt 0 ]; then
    retry run_install "$@"
fi
rm -f "$log"
