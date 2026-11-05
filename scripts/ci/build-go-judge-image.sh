#!/usr/bin/env bash
set -euo pipefail

: "${1:?image tag required}"
image=$1
repository_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"

docker build -t "$image" go-judge
./scripts/ci/check-go-judge-image.sh "$image"
