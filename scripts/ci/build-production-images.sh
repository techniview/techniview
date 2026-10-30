#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"

docker build -f backend/Dockerfile.prod -t techniview-backend:ci backend
docker build -f frontend/Dockerfile.prod -t techniview-frontend:ci frontend
docker build --target direct -t techniview-go-judge:ci internal-judge0-fork
./scripts/ci/check-go-judge-image.sh techniview-go-judge:ci
