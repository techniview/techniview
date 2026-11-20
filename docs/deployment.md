# GPU deployment

The supported pilot setup runs the frontend, API, workers, MySQL, monitoring,
and go-judge on the GPU host. It needs Docker Compose access, `openssl`, and
`curl`; it does not need sudo. Docker itself must be able to run privileged
containers with cgroup v2 for go-judge.

## First setup

From the repository checkout on the GPU host:

```sh
./scripts/gpu-deploy init
```

On its first run, this creates `.env.production` with mode `0600`, sets the GPU
hostname, and generates a Grafana password. Review `PUBLIC_HOST` and change it
if needed. The default email mode is `capture`, so Resend is not required for
pilot testing. It creates missing secrets under
`$HOME/.local/share/techniview/secrets`, prepares Docker-managed copies for the
NFS-backed home directory, builds the app images from this checkout, starts the
services, waits for health checks, and seeds the demo accounts once. It does
not replace existing secrets or remove database data.

Demo sign-ins:

- Teacher: `teacher@techniview.local` / `teacher-demo`
- Student: `student@techniview.local` / `student-demo`

These are fixed test credentials. Keep the deployment limited to the intended
VPN audience and remove or change the demo accounts before any broader access.

## Everyday commands

```sh
./scripts/gpu-deploy doctor
./scripts/gpu-deploy deploy
./scripts/gpu-deploy status
./scripts/gpu-deploy logs backend app_worker go-judge
./scripts/gpu-deploy mail
./scripts/gpu-deploy down
```

`deploy` rebuilds the backend and frontend from the current checkout. `down`
stops containers but preserves named volumes. Do not use `docker compose down
--volumes` unless you intend to erase persistent data. To use a different env
file, set `TECHNIVIEW_ENV_FILE=/path/to/file` before invoking the script.

The script copies source secrets and monitoring configuration into Docker
volumes because the system Docker daemon cannot bind-mount the GPU host's NFS
home. These volumes survive container recreation. The preparation script refuses
to overwrite a changed secret already copied into a Docker volume; secret
rotation needs an explicit volume update procedure. Keep the source files in
your private home directory and do not print their contents into shared logs.

## Public URL

The app listens on `127.0.0.1:8080` by default. The GPU host's HTTPS proxy must
route both `/techniview` and `/techniview/*` to `http://127.0.0.1:8080` while
preserving the path prefix. `doctor` checks the local app route; it cannot add
the campus proxy route or make an unreachable public port available. If port
8080 is occupied, change `FRONTEND_PORT` in `.env.production` and have the
proxy operator target that port.

Grafana is available on `127.0.0.1:3000`; use an SSH tunnel to view it. MySQL,
Prometheus, and go-judge have no published host ports. The runner is privileged
and shares a host with application data in this pilot layout. Restrict Docker
access to trusted operators and keep the deployment behind the campus VPN.

## Configuration

The checked-in `.env.production.example` contains the supported settings and
chosen starting capacity: 16 go-judge execution slots, a 24-CPU runner quota,
four app-worker replicas with four processes each, and two API workers. The
runner quota is a ceiling, not a reservation. Change `PUBLIC_HOST` before
initial setup. Change `FRONTEND_PORT` only if needed. The script generates
database passwords and an email signing key; do not copy them into the env file.

Email capture writes messages to a persistent Docker volume. `./scripts/gpu-deploy
mail` prints captured messages, including sign-in and recovery links. Treat that
output as sensitive. To enable Resend later, create the `resend_api_key` secret
file, configure the sender and email mode, then follow the documented secret
volume rotation procedure before restarting workers.

The optional complexity worker stays idle unless `BIG_O_OLLAMA_URL` points to
an Ollama service reachable from the stack. Configure its model and timeout in
`.env.production` if needed.

## Troubleshooting

- `init` or `deploy` reports secret mismatch: the source file differs from the
  Docker-managed copy. Do not delete the volume blindly; confirm the existing
  database's credentials, then update the secret volume deliberately.
- Services fail health checks: inspect `./scripts/gpu-deploy logs` and
  `./scripts/gpu-deploy status`. The host must support cgroup v2 and the
  privileged runner configuration.
- The local URL works but the public URL does not: ask the GPU host operator to
  configure the HTTPS route and preserve `/techniview`.
- Login or nested page refresh fails: verify the path prefix is preserved by
  the proxy and `PUBLIC_HOST` matches the public hostname.

Database backup and restore remain a separate follow-up. Until then, treat the
MySQL volume as persistent but not backed up. Before enrolling participants,
set up encrypted off-host backups and verify a restore. See
[database recovery](database-recovery.md) for the current manual procedures.
