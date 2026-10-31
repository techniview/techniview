#!/usr/bin/env bash
set -euo pipefail
image=${1:?go-judge image is required}
docker run --rm --network none --entrypoint sh "$image" -ec '
  ! command -v ruby
  ! command -v isolate
  go-judge -version
  test -x /usr/bin/prlimit
  /opt/python/bin/python3.14 -I -B - <<'PY'
import bz2
import ctypes
import decimal
import hashlib
import lzma
import math
import sqlite3
import ssl
import subprocess
import tempfile
import uuid
from pathlib import Path

assert ssl.create_default_context().cert_store_stats()["x509_ca"] >= 100

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / "child-output"
    child = subprocess.run(
        ["/opt/python/bin/python3.14", "-c", "print(123)"],
        check=True,
        capture_output=True,
        text=True,
    )
    output.write_text(child.stdout, encoding="utf-8")
    assert output.read_text(encoding="utf-8") == "123\n"
PY
  test ! -d /opt/python/include
  test ! -d /opt/python/lib/python3.14/test
'
