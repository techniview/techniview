#!/usr/bin/env bash
set -euo pipefail

if command -v actionlint >/dev/null 2>&1; then
  actionlint
elif command -v docker >/dev/null 2>&1; then
  docker run --rm --network none -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.7
else
  echo "actionlint or Docker is required to lint GitHub workflows." >&2
  exit 1
fi

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -S warning .githooks/pre-commit scripts/setup-hooks.sh scripts/ci/*.sh \
    scripts/backup-mysql.sh internal-judge0-fork/worker-entrypoint.sh \
    internal-judge0-fork/api/docker-entrypoint.sh \
    internal-judge0-fork/api/scripts/server internal-judge0-fork/api/scripts/workers
else
  echo "shellcheck is required to lint shell scripts." >&2
  exit 1
fi
