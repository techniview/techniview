# Application database backup and restore

The application database is MySQL. It holds accounts, course rosters, assignments,
submissions, worker claims, and derived progress. Keep backups outside the server
and protect them as student records. Keep the email signing key and research export
secret separately; restoring the database without the original keys invalidates
pending email links and changes research pseudonyms.

For a consistent maintenance backup on a single-host Compose installation, stop
application writes, then stream a dump to a protected file on the host:

```sh
docker compose stop backend app_worker
umask 077
docker compose exec -T mysql sh -c 'exec mysqldump --single-transaction --routines --triggers -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' > techniview-backup.sql
docker compose start backend app_worker
```

To restore, use a new or stopped deployment with the same application secrets.
Take a separate backup of the target database first. The restore replaces its
contents, so do not run it against a database you intend to keep:

```sh
docker compose stop backend app_worker
docker compose exec -T mysql sh -c 'exec mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < techniview-backup.sql
docker compose start backend app_worker
```

The backend startup runs Alembic migrations and the idempotent demo seed. Check
`/api/health` after restart and inspect worker logs for any submissions that
were in flight when the backup was taken. A backup taken with both application
processes stopped avoids new TechniView writes, but Judge0 may still finish an
already dispatched case while the API is down. The worker polls Judge0 after
restart and marks cases it cannot recover as infrastructure errors after its
recovery deadline.
