# Application database backup and restore

The application VM's MySQL database holds accounts, rosters, assignments,
submissions, worker claims, and derived progress. Treat backups as student
records. Encrypt them and store them outside the application VM. Keep
`EMAIL_SIGNING_KEY` and any research export secret in a separate protected
backup. Restoring without the original keys invalidates pending email links and
changes research pseudonyms.

## Create a backup

Run this on the application VM. `--single-transaction` creates a consistent dump
for the InnoDB tables without stopping application writes. Use a unique,
permission-restricted output directory, then encrypt and copy the dump to the
campus backup destination.

```sh
umask 077
backup_file="techniview-$(date -u +%Y%m%dT%H%M%SZ).sql"
docker compose --env-file .env.production -f compose.production.yml \
  exec -T mysql sh -c \
  'set -eu
  MYSQL_PWD=$(cat "${MYSQL_PASSWORD_FILE:?}"); export MYSQL_PWD
  exec mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF \
  --routines --triggers -u "$MYSQL_USER" "$MYSQL_DATABASE"' \
  > "$backup_file.partial" && mv "$backup_file.partial" "$backup_file"
```

A failed dump stays marked `.partial`; do not transfer or restore it. Remove it
after investigating the failure.

The campus backup system should run this hourly, encrypt before transfer, retain
the agreed history, and alert if the latest successful copy is more than 90
minutes old. Never place an unencrypted dump in a shared or web accessible path.

For backups stored with the included restic timer, list the snapshot contents and
write the chosen SQL dump to a permission-restricted file before restoring:

```sh
sudo bash -c 'set -a; . /etc/techniview/backup.env; set +a; restic ls latest'
umask 077
sudo bash -c 'set -a; . /etc/techniview/backup.env; set +a; restic dump latest /techniview.sql' \
  > techniview-backup.sql
```

Replace the filename with one shown by `restic ls`. Keep the extracted dump
protected and remove it after recovery.

## Restore a backup

Restore to a new or stopped deployment with the same application secrets. Take a
separate backup of the target database first. The restore replaces its contents.

```sh
docker compose --env-file .env.production -f compose.production.yml \
  stop backend app_worker
docker compose --env-file .env.production -f compose.production.yml \
  exec -T mysql sh -c \
  'set -eu
  MYSQL_PWD=$(cat "${MYSQL_PASSWORD_FILE:?}"); export MYSQL_PWD
  exec mysql -u "$MYSQL_USER" "$MYSQL_DATABASE"' \
  < techniview-backup.sql
docker compose --env-file .env.production -f compose.production.yml \
  start backend app_worker
```

Check `/api/health` after restart and inspect worker logs for submissions that
were in flight during the restore. Runner state lives on a separate VM. The app
worker polls Judge0 after restart, and marks unrecoverable cases as infrastructure
errors after the configured recovery deadline.
