#!/usr/bin/env bash
set -euo pipefail

api_image=${1:?API image is required}
worker_image=${2:?Worker image is required}
api_budget=$((250 * 1024 * 1024))
worker_budget=$((350 * 1024 * 1024))

check_size() {
  local image=$1 budget=$2 size
  size=$(docker image inspect --format '{{.Size}}' "$image")
  printf '%s: %s bytes (budget %s bytes)\n' "$image" "$size" "$budget"
  if ((size > budget)); then
    echo "Runner image exceeds its size budget." >&2
    exit 1
  fi
}

check_size "$api_image" "$api_budget"
check_size "$worker_image" "$worker_budget"
for image in "$api_image" "$worker_image"; do
  docker run --rm --network none --entrypoint sh "$image" -ec '
    for command in gcc g++ make git node npm java javac dotnet sudo cron; do
      if command -v "$command" >/dev/null; then
        echo "Unexpected runtime tool: $command" >&2
        exit 1
      fi
    done
    find /api -name "*.rb" -print0 | xargs -0 -n 1 ruby -c
    ruby -e '\''abort "Unsupported Ruby" unless RUBY_VERSION.start_with?("3.4.")'\''
    bundle check
  '
done

docker run --rm --network none --entrypoint sh "$api_image" -ec '
  ! command -v isolate
  ! command -v python3
  test ! -d /opt/python
'
docker run --rm --network none --entrypoint sh "$worker_image" -ec '
  ! command -v isolate
  go-judge -version
  python3.14 -I -B -c "import bz2, ctypes, decimal, hashlib, lzma, math, sqlite3, ssl, uuid; print(ssl.OPENSSL_VERSION)"
  test ! -d /opt/python/include
  test ! -d /opt/python/lib/python3.14/test
'
