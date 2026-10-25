# Campus deployment

TechniView runs as two independent Docker Compose projects on separate campus
Linux VMs. The application VM runs Caddy, FastAPI, the application worker, and
MySQL. The runner VM runs Judge0, its worker, PostgreSQL, and Redis. The runner
VM executes untrusted student code and must not share a host with student data.

## Campus network requirements

- Publish ports 80 and 443 on the application VM for the website and HTTPS.
- Bind the Judge0 API to the runner VM's private address. Allow inbound port 2358
  only from the application VM's private address.
- Allow the runner VM to make outbound HTTPS requests to the application
  hostname for Judge0 callbacks. Callbacks use TLS and per-case random tokens.
- Do not publish MySQL, PostgreSQL, Redis, or the runner worker ports.
- Point the public DNS name at the application VM. Caddy obtains and renews the
  HTTPS certificate, so ports 80 and 443 must be reachable for certificate
  validation.

Request an initial 4 vCPU / 8 GiB application VM and an 8 vCPU / 16 GiB runner
VM. Set `API_WORKERS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, and
`APP_WORKER_REPLICAS` in `.env.production` after load testing. API workers handle
concurrent HTTP requests; the database pool settings bound each process's
connections and must fit under MySQL's connection limit; application worker
replicas claim and process queued submissions concurrently. Allocate enough CPU
and memory for the selected counts. The Compose files cap service CPU and memory
use within those budgets. Treat these as starting sizes
and adjust them from the assignment load test.

The application worker retries Judge0 `429` dispatch rejections up to five
times, with exponential backoff and jitter. `WORKER_DISPATCH_MAX_RETRIES`,
`WORKER_RETRY_BASE_SECONDS`, `WORKER_RETRY_MAX_SECONDS`, and
`WORKER_RETRY_AFTER_MAX_SECONDS` set the retry policy. A run that still receives
`429` after those retries completes with `failure_code=runner_busy`; the API
marks it retryable and tells the student to try again later. The worker does not
resend a dispatch after a timeout or lost response. Judge0 may have accepted
that request, so TechniView waits for the callback and then reports an unknown
outcome if the recovery window expires.

Use encrypted campus storage for both VMs. Judge0 keeps copies of submitted code
and execution output in its own database, so protect and retain that volume as
student data too.

The runner needs Linux kernel 6.1 or newer and cgroup v2. Its worker requires
privileged mode for Isolate, with a private cgroup namespace and no host
cgroup bind mount. Keep it on the
dedicated runner VM, patch the VM promptly, restrict SSH to campus administrators,
and never give application users access to the Docker daemon. The web-facing
Judge0 server does not need host cgroup access or privileged mode.

## Configure each VM

Check out the same reviewed release on both VMs. Keep the Compose files and
application code read-only to the service accounts. Create private environment
files from the matching examples. Each file contains only that VM's credentials.
Set their permissions to `0600`; do not copy either file into Git or a shared
backup that lacks access controls.

On the application VM, create `/etc/techniview/secrets` with mode `0700` and
create these files with unique values: `mysql_root_password`, `mysql_password`,
`email_signing_key` (at least 32 random bytes), and `resend_api_key`. Make the
files readable inside the non-root API container, for example owner `root` and
mode `0444`; the parent directory remains accessible only to root. The Compose
stack mounts each secret only into the services that need it.

Generate the database passwords and signing key with `openssl rand -hex 32`.
Put the verified provider key in `resend_api_key`. Keep the complete secret
directory backed up using campus-approved encrypted secret storage.

On the runner VM, set `RUNNER_PRIVATE_BIND_IP` to its private interface address.
Create `/etc/techniview-runner/secrets` with mode `0700`, then create unique
`postgres_password` and `redis_password` files with mode `0444`. The runner
containers read these Compose secrets at startup. Start the runner:

```sh
docker compose --env-file .env.runner.production \
  -f compose.runner.production.yml pull
docker compose --env-file .env.runner.production \
  -f compose.runner.production.yml up -d
docker compose --env-file .env.runner.production \
  -f compose.runner.production.yml ps
```

On the application VM, set `RUNNER_PRIVATE_HOST` to the runner's private address,
`PUBLIC_HOST` to the DNS name, and unique MySQL and email secrets. Start the app:

```sh
docker compose --env-file .env.production \
  -f compose.production.yml pull
docker compose --env-file .env.production \
  -f compose.production.yml up -d
docker compose --env-file .env.production \
  -f compose.production.yml ps
```

The application startup applies Alembic migrations and imports the reviewed
problem catalog. It does not create demo users. Provision the first professor
interactively:

```sh
docker compose --env-file .env.production -f compose.production.yml \
  exec backend python -m scripts.provision_instructor \
  "Professor Name" professor@example.edu
```

Keep `EMAIL_SIGNING_KEY` stable across restarts. Email delivery requires a sender
verified with Resend. `RESEARCH_EXPORT_SECRET` is not needed for normal operation.

## Image releases, updates, and rollback

Push a reviewed `v*` tag to run CI and publish the backend, frontend, runner-api,
and runner-worker images to GitHub Container Registry. Each image is tagged with the source commit
SHA. Set that same SHA as `IMAGE_TAG` in both VM environment files. Give each VM
read-only access to the packages, then pull and start the runner first. Confirm
`/about` works from the application VM, then pull and start the app. The host
does not build images.

Back up MySQL and the application secrets before each update. The API applies
database migrations at startup, so run one backend replica during updates. If
an app release fails, return to the previous image tag only when its code
supports the current database revision. Alembic downgrade is not an automatic
rollback strategy.

## Backups and recovery

Back up the MySQL application database hourly to encrypted campus storage outside
the application VM. Keep signing and export secrets in a separate protected
backup. Judge0's PostgreSQL and Redis contain execution state, not the grading
record; after losing runner state, in-flight cases recover through callbacks or
eventually become infrastructure errors under the worker recovery policy.

The repo includes an hourly `restic` backup script and systemd timer. Install
`restic` with `backup --stdin-from-command` support on the application VM, configure an encrypted campus repository in
`/etc/techniview/backup.env`, set up its SSH key if using the SFTP backend, then
install the service files from `deploy/systemd/`. Initialize the repository once
with `restic init` using that environment file. Enable the timers:

```sh
sudo install -d -m 0700 /etc/techniview
sudo install -m 0600 .env.backup.example /etc/techniview/backup.env
sudo install -m 0644 deploy/systemd/*.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now techniview-backup.timer
sudo systemctl enable --now techniview-backup-prune.timer
sudo systemctl start techniview-backup.service
```

Before enabling the service, edit `backup.env`, create the file named by
`RESTIC_PASSWORD_FILE` with mode `0600`, and point
`TECHNIVIEW_APP_ENV_FILE` at the app environment file. Keep the checkout at
`/opt/techniview/current` or set `TECHNIVIEW_COMPOSE_FILE` to the Compose file
path. Initialize the repository once with:

```sh
sudo bash -c 'set -a; . /etc/techniview/backup.env; set +a; restic init'
```

The dump reads the mounted MySQL password inside the container. Restic runs the
dump command directly and saves no snapshot if it fails. Snapshots use the stable
path `/techniview.sql` so retention groups all database backups together. The
systemd services use a writable cache at `/var/cache/techniview-restic`.

Run `python3 scripts/tests/test_backup_mysql.py` with Docker and restic installed
to check backup, restore, authentication failure, and partial dump rejection
against a disposable database.

The service stores hourly snapshots for a day, daily snapshots for a month,
weekly snapshots for three months, and monthly snapshots for a year. Confirm the
first snapshot appears in the off-host repository and test a restore before the
pilot. The timer does not encrypt environment or signing key files; back those up
separately using campus-approved secret storage.

Use [the database recovery guide](database-recovery.md) for consistent dumps and
restore steps. Test a restore on an isolated VM before the pilot and on a regular
schedule. Alert the project team if the latest off-host backup is more than 90
minutes old.

## Operations signals

The backend exposes Prometheus text metrics at `/api/metrics`. It includes
request totals and latency histograms by method, route template, and status;
submission counts by status and practice-run type; queued submission depth and
age; case counts by dispatch phase; and live Judge0 Resque worker counts by
queue and state (`available`, `idle`, `working`, and `paused`), plus each queue's
depth. `techniview_judge0_worker_status_scrape_success` indicates whether the
backend could fetch the live runner status. Scrape this endpoint from a
Prometheus-compatible collector on the app Docker network. Caddy returns 404
for this path on the public hostname. Runner retry gauges include persisted
dispatch retries, current poll failures, submissions that ended busy, and
submissions whose dispatch outcome could not be confirmed.

The persisted `techniview_execution_cases{phase="running_on_judge0"}` gauge is
the number of cases whose latest recorded Judge0 status is `Processing`; it can
miss short executions between application polls. Use the live
`techniview_judge0_workers{state="working"}` gauge to track actual runner worker
utilization.

The Compose projects use Docker's rotating `local` log driver and retain the
latest three 10 MiB files per service. The API and app worker write JSON events
to stdout. API request records include
the request ID, route template, status, and duration. Worker records cover
claim, Judge0 dispatch/failure, and completion. They intentionally omit source
code, callback credentials, and student identifiers. Forward these logs to the
campus log collector before a pilot if longer retention or centralized alerts
are required.

## Launch gates

The runner now builds from Debian 13, Ruby 3.4, Rails 8.1, Python 3.14 and
Isolate 2.7. Scan the release images and pass the real execution integration
suite on the campus VM before the pilot. The Isolate worker still needs
`privileged` mode, confined to its private cgroup namespace. Campus IT should
review the dedicated VM boundary before student code is accepted.

Drain pending runner jobs before replacing the old images: the refreshed fork
uses a new queue name. Back up PostgreSQL and keep the previous images for
rollback. The existing schema migrations and Python language ID are retained.

Before enrolling participants, confirm campus DNS and firewall rules, approved
email delivery, SSO requirements, research data handling requirements with the
IRB advisor, the retention period for Judge0's duplicate source and output data,
and a successful backup restore. Load test the pilot profile in a disposable
environment. CI runs a 1,000-student synchronized burst with one real case per
submission. GitHub-hosted results are useful for regressions but do not establish
campus capacity; repeat the profile on the proposed campus VM sizes before the
pilot. The runner queue limit defaults to 12,000 cases to hold that profile with
headroom. Reduce it only if the planned peak load is lower and queue backpressure
is intentional.
