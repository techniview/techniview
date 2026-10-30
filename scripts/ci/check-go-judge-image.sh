#!/usr/bin/env bash
set -euo pipefail
image=${1:?go-judge image is required}
docker run --rm --network none --entrypoint sh "$image" -ec '
  ! command -v ruby
  ! command -v isolate
  go-judge -version
  /opt/python/bin/python3.14 -I -B -c "import bz2, ctypes, decimal, hashlib, lzma, math, sqlite3, ssl, uuid"
  test ! -d /opt/python/include
  test ! -d /opt/python/lib/python3.14/test
'
