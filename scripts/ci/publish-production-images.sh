#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"
: "${GITHUB_ACTOR:?GITHUB_ACTOR is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"

repository_root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
image_namespace="ghcr.io/${GITHUB_REPOSITORY,,}"
cd "$repository_root"

printf '%s' "$GITHUB_TOKEN" | docker login ghcr.io \
  --username "$GITHUB_ACTOR" --password-stdin

docker build -f backend/Dockerfile.prod \
  -t "$image_namespace/backend:$GITHUB_SHA" backend
docker build -f frontend/Dockerfile.prod \
  -t "$image_namespace/frontend:$GITHUB_SHA" frontend
docker build -t "$image_namespace/go-judge:$GITHUB_SHA" go-judge
./scripts/ci/check-go-judge-image.sh "$image_namespace/go-judge:$GITHUB_SHA"

docker push "$image_namespace/backend:$GITHUB_SHA"
docker push "$image_namespace/frontend:$GITHUB_SHA"
docker push "$image_namespace/go-judge:$GITHUB_SHA"
