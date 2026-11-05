#!/usr/bin/env bash
set -euo pipefail

base=${1:-}

if [ -z "$base" ] || [ "$base" = "0000000000000000000000000000000000000000" ]; then
    git fetch --quiet origin main
    base=$(git merge-base origin/main HEAD)
fi

if ! git cat-file -e "$base^{commit}" 2>/dev/null; then
    git fetch --quiet origin "$base"
fi

if git diff --quiet "$base" HEAD -- backend frontend go-judge scripts/ci; then
    echo false
else
    echo true
fi
