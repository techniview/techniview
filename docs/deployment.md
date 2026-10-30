# Campus deployment

TechniView runs as two independent Docker Compose projects on separate campus
Linux VMs. The application VM runs Caddy, FastAPI, the application worker, and
MySQL. The runner VM runs standalone go-judge. The runner
VM executes untrusted student code and must not share a host with student data.

## Campus network requirements

- Publish ports 80 and 443 on the application VM for the website and HTTPS.
- Bind go-judge to the runner VM's private address. Allow inbound port 5050
  only from the application VM's private address.
- Do not publish MySQL or any other runner port.
- Point the public DNS name at the application VM. Caddy obtains and renews the
  HTTPS certificate, so ports 80 and 443 must be reachable for certificate
  validation.

Request an initial 4 vCPU / 8 GiB application VM and an 8 vCPU / 16 GiB runner
VM. Set `API_WORKERS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, and
`APP_WORKER_REPLICAS` and `DIRECT_WORKER_PROCESSES` in `.env.production` after load testing. API workers handle
concurrent HTTP requests; the database pool settings bound each process's
connections and must fit under MySQL's connection limit; application worker
replicas claim and process queued submissions concurrently. Allocate enough CPU
and memory for the selected counts. The Compose files cap service CPU and memory
use within those budgets. Treat these as starting sizes
and adjust them from the assignment load test.

The application commits each case attempt before calling go-judge. After a worker
crash or ambiguous response, recovery marks that case unknown without rerunning
it. Remaining unstarted cases continue after the worker lease expires.

Use encrypted campus storage for both VMs. TechniView stores submission code and
results in MySQL. The execution service does not keep a second submission database.

The runner needs Linux kernel 6.1 or newer and cgroup v2. Its worker requires
privileged mode for go-judge, with a private cgroup namespace and no host
cgroup bind mount. Keep it on the
dedicated runner VM, patch the VM promptly, restrict SSH to campus administrators,
and never give application users access to the Docker daemon. Expose the go-judge port only on the private app-to-runner interface.

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
The runner needs no separate database or secret files. Start the runner:

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

Push a reviewed `v*` tag to run CI and publish the backend, frontend, and
go-judge images to GitHub Container Registry. Each image is tagged with the source commit
SHA. Set that same SHA as `IMAGE_TAG` in both VM environment files. Give each VM
read-only access to the packages, then pull and start the runner first. Confirm `/version` on the runner private port works from the application VM, then pull and start the app. The host
does not build images.

Back up MySQL and the application secrets before each update. The API applies
database migrations at startup, so run one backend replica during updates. If
an app release fails, return to the previous image tag only when its code
supports the current database revision. Alembic downgrade is not an automatic
rollback strategy.

## Backups and recovery

Back up the MySQL application database hourly to encrypted campus storage outside
the application VM. Keep signing and export secrets in a separate protected
backup. A lost runner response leaves the affected case with an unknown outcome.

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

The backend exposes Prometheus text metrics at `/api/metrics`, including API
request latency, submission status, queue depth, and queue age. Scrape this
endpoint from the app Docker network. The direct execution path does not expose
Judge0 Resque worker metrics. Monitor go-judge through container health, CPU,
memory, and restart counts.

The Compose projects use Docker's rotating `local` log driver and retain the
latest three 10 MiB files per service. The API and app worker write JSON events
to stdout. API request records include
the request ID, route template, status, and duration. Worker records cover
claim, sandbox execution failure, and completion. They intentionally omit source
code, callback credentials, and student identifiers. Forward these logs to the
campus log collector before a pilot if longer retention or centralized alerts
are required.

## Launch gates

The runner image pins go-judge 1.13.3 and Python 3.14.8. Run the real execution,
resource-limit, and worker-restart tests on the target VM before accepting student
code. The runner requires privileged mode for its private cgroup namespace;
restrict its port to the application VM.

Before enrolling participants, confirm DNS and firewall rules, email delivery,
research data handling, a successful backup restore, and a load test on the
allocated VMs. The A100 comparison favored direct execution on the tested
Ransom Note workload; its small bursts do not establish production p99.
