# TechniView Python runner

This directory owns the runner source and its builds. It derives the submission
API and queue behavior from Judge0, but builds directly on a digest-pinned Ruby
3.4 / Debian 13 slim base. No Judge0 or multi-language compiler image is pulled
at any build stage. See [PROVENANCE.md](PROVENANCE.md) and [LICENSE](LICENSE).

## What ships

The Dockerfile has two production targets:

| Target | Contents | Use |
| --- | --- | --- |
| `api` | Ruby, required Rails 8.1 components, locked gems, PostgreSQL client library, local API source | Accept submissions and serve results |
| `worker` | API runtime plus Python 3.14.8, Isolate 2.7 and their shared libraries, process management tools | Execute queued Python jobs |

Build tools exist only in intermediate stages. The final images exclude C/C++
compilers, Node, Java, other submission languages, Git, sudo, cron, telemetry,
Python packaging tools, Python test modules, and documentation generators.
Python retains its standard library, including SSL, SQLite, compression and
ctypes support. Only its interpreter and runtime libraries are copied out of
the build stage. The API image has no Python interpreter or sandbox binary.

## Build and run

```sh
docker build --target api -t techniview-runner-api:local internal-judge0-fork
docker build --target worker -t techniview-runner-worker:local internal-judge0-fork
./scripts/ci/check-runner-images.sh techniview-runner-api:local techniview-runner-worker:local
docker compose up -d --build server workers db redis
```

The check script enforces uncompressed image budgets of 250 MiB for the API and
350 MiB for the worker, checks Ruby syntax and installed dependencies, and rejects
unexpected compilers and tooling. These budgets leave room for security patches.
The build context excludes tests and maintenance documentation.

Production uses `compose.runner.production.yml`. Release CI publishes
`runner-api` and `runner-worker` packages under the same GHCR namespace as the
application, tagged by source commit. A separate GitHub repository is optional;
it is not needed to build or publish either image.

## Sandbox and host requirements

Use a dedicated Linux runner VM with kernel 6.1 or newer, cgroup v2, and Docker
with private cgroup namespace support. The API runs as UID 1000 without
privileges. The worker starts privileged to initialize its own delegated cgroup
subtree, then runs the queue process as UID 1000. Only the Isolate helper retains
its required setuid permission. Do not enable `no-new-privileges` on the worker.

The worker requires `cgroup: private`. It fails startup when cgroup delegation
is unavailable. It never binds the host's `/sys/fs/cgroup` into the container.
It remains a privileged container, so keep the dedicated VM and campus firewall
boundary. Expose only the API's private port to the application VM.

Each sandbox has a locked slot, distinct UID, network namespace, CPU/wall-time,
aggregate memory, process-count and output-file limits. It receives only Python,
shared libraries, its own working directory and temporary directory. API files,
credentials, Ruby, shell executables and the worker's filesystem are not mapped
into the sandbox. Worker startup never prints credentials.

## API and data

The API exposes `POST /submissions`, `GET /submissions/:token`, `/about`, and
`/workers`. Source, standard input, expected output, resource limits, callbacks,
base64 encoding and `wait=true` retain the application contract. Waiting requests
still enqueue work; the API never executes a submission itself. Language
selection, network enablement, uploaded archives and compiler options are
rejected. The only active language is defined in `languages/active.rb`.

PostgreSQL migrations retain the existing runner schema. Startup migrates and
updates the Python language record without deleting submission history. Back up
the runner database before upgrading and drain the old queue first: queue names
now use the internal runner version rather than the upstream Judge0 version.
Keep the old release available until the new runner passes its execution checks.

The entrypoint reads `postgres_password`, `redis_password` and optional
`authn_token` files from `/run/secrets`. Development can use environment values.
The application VM's firewall restriction is required even when an API token is
configured. Execution callbacks retain the application-generated per-case token.

## Maintenance and verification

Edit the source in `api/` directly. The old controller patch and external source
image stage are gone. Ruby dependencies are recorded in `api/Gemfile.lock`;
update that lockfile on Ruby 3.4 when changing the Gemfile. Review the slim base
digest and the Python and Isolate source versions/checksums together.

Run `make integration` on the supported Linux host. This starts disposable
PostgreSQL, Redis, MySQL and application containers, then checks real execution,
callbacks, recovery, concurrent submissions and sandbox limits. The direct
runner tests also cover CPU/memory/output limits, forbidden runtime fields,
network isolation and inaccessible application/secret paths. Do not waive these
checks based only on a successful image build.
