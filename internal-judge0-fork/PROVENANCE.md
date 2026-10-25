# Runtime source provenance

The API files in `api/` were imported from the required runtime portions of
https://github.com/mrkushalsm/judge0 at
`f39f5cd405d2b6c3d479efdf7488059b275ac29a` (Judge0 1.13.1 with cgroup v2 support).
They are maintained here under the included GPL-3.0 license. TechniView's
Python-only language and API changes are applied directly to this source.

Only the submission API, queue worker, serializers, models, and database
migrations are included. Multi-language catalogs, documentation generators,
telemetry, cron jobs, development tools, and compiler bundles are excluded.

Isolate is built from source at commit
`8f185bb37f3f23e29b33b0c7727c91c13429abe3` (2.7). Its source archive and checksum
are pinned in the Dockerfile; its GPL-2.0 license is included in the worker image.
Python is built from its checksum-verified official 3.14.8 source archive and
ships its license. Ruby uses the digest-pinned official slim Debian 13 image.
