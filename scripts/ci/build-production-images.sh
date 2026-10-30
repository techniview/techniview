#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"

docker build -f backend/Dockerfile.prod -t techniview-backend:ci backend
docker build -f frontend/Dockerfile.prod -t techniview-frontend:ci frontend
docker build -t techniview-go-judge:ci go-judge
./scripts/ci/check-go-judge-image.sh techniview-go-judge:ci
