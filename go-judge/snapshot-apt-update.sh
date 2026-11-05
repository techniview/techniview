#!/bin/sh
set -eu

attempts=5
backoff=20

check_output() {
    case "$1" in
        *"Failed to fetch"* | *"Some index files failed"* | *"Connection failed"* | *"Gateway Timeout"* | *"TooManyRequests"* | *"No healthy backends"* | *"E: "*) return 1 ;;
        *) return 0 ;;
    esac
}

apt_retry_update() {
    output=$(apt-get update 2>&1 || true)
    printf '%s\n' "$output"
    check_output "$output"
}

apt_retry_install() {
    output=$(apt-get install -y --no-install-recommends "$@" 2>&1 || true)
    printf '%s\n' "$output"
    check_output "$output"
}

run_with_retries() {
    attempt=1
    until "$@"; do
        if [ "$attempt" -ge "$attempts" ]; then
            printf 'snapshot.debian.org sources still failing after %s attempts\n' "$attempts" >&2
            exit 1
        fi
        sleep "$backoff"
        backoff=$((backoff * 2))
        attempt=$((attempt + 1))
    done
}

rm -f /etc/apt/sources.list.d/debian.sources
run_with_retries apt_retry_update
if [ "${1:-}" = "install" ]; then
    shift
fi
if [ "$#" -gt 0 ]; then
    run_with_retries apt_retry_install "$@"
fi
rm -rf /var/lib/apt/lists/*
