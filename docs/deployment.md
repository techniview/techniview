# Single-host deployment

The production stack uses Caddy to serve the built frontend and proxy `/api` to
FastAPI over the private Compose network. Only ports 80 and 443 are published.
Caddy obtains and renews a certificate for `PUBLIC_HOST`; point that DNS name to
the host before starting the stack. Judge0 still requires privileged cgroup access
on the host.

Copy `.env.production.example` to a private environment file and replace every
placeholder with a unique value. Set `PUBLIC_HOST` to the public DNS name and
`EMAIL_FROM` to a sender verified with Resend. Keep this file outside version
control. Review firewall rules and protect the host and Compose volumes before
enrolling real students.

```sh
docker compose --env-file .env.production -f compose.production.yml up -d --build
docker compose --env-file .env.production -f compose.production.yml ps
```

The backend applies migrations and imports the 500-problem catalog before it
becomes healthy. The worker starts afterward. The startup process does not load
demo accounts. Create the first professor from an interactive operator shell:

```sh
docker compose --env-file .env.production -f compose.production.yml exec backend \
  python -m scripts.provision_instructor "Professor Name" professor@example.edu
```

The command prompts for an initial password. The professor can then log in and
create classes. Email delivery requires a working Resend key and verified sender.
Keep the `EMAIL_SIGNING_KEY` stable across restarts so pending links remain valid.
Set `RESEARCH_EXPORT_SECRET` only for the protected export command described in
[backend reporting](backend-reporting.md).

Back up the MySQL volume and the application secrets before changing the stack.
Use the [database recovery guide](database-recovery.md) for a consistent dump and
restore. For the production stack, add
`--env-file .env.production -f compose.production.yml` to each `docker compose`
command in that guide. Store backups outside the host and check a restore on a
separate installation before relying on them.
