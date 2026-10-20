#!/bin/bash
set -euo pipefail

: "${TECHNIVIEW_APP_ENV_FILE:?Set TECHNIVIEW_APP_ENV_FILE}"
compose_file=${TECHNIVIEW_COMPOSE_FILE:-compose.production.yml}
repository_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)

cd "$repository_root"
# Variables in the command are expanded inside the MySQL container.
# shellcheck disable=SC2016
restic backup --stdin-filename techniview.sql --stdin-from-command -- \
  docker compose --env-file "$TECHNIVIEW_APP_ENV_FILE" -f "$compose_file" \
  exec -T mysql sh -c \
  'set -eu
  MYSQL_PWD=$(cat "${MYSQL_PASSWORD_FILE:?MYSQL_PASSWORD_FILE is required}")
  export MYSQL_PWD
  exec mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF \
    --routines --triggers -u "$MYSQL_USER" "$MYSQL_DATABASE"'
