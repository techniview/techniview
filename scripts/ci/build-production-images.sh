#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"

docker build -f backend/Dockerfile.prod -t techniview-backend:ci backend
docker build -f frontend/Dockerfile.prod -t techniview-frontend:ci frontend
docker build --target api -t techniview-runner-api:ci internal-judge0-fork
docker build --target worker -t techniview-runner-worker:ci internal-judge0-fork
./scripts/ci/check-runner-images.sh techniview-runner-api:ci techniview-runner-worker:ci
