#!/bin/sh
set -eu

for name in POSTGRES_PASSWORD REDIS_PASSWORD AUTHN_TOKEN; do
    path="/run/secrets/$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
    if [ -f "$path" ]; then
        export "$name=$(cat "$path")"
    fi
done
export POSTGRES_HOST="${POSTGRES_HOST:-db}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_DB="${POSTGRES_DB:-postgres}"
export POSTGRES_USER="${POSTGRES_USER:-postgres}"
export REDIS_HOST="${REDIS_HOST:-redis}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export AUTHN_HEADER="${AUTHN_HEADER:-X-Auth-Token}"
export AUTHZ_HEADER="${AUTHZ_HEADER:-X-Auth-User}"
export RAILS_ENV=production
export RAILS_MAX_THREADS="${RAILS_MAX_THREADS:-4}"
export RAILS_SERVER_PROCESSES="${RAILS_SERVER_PROCESSES:-0}"
export SECRET_KEY_BASE="${SECRET_KEY_BASE:-$(ruby -rsecurerandom -e 'print SecureRandom.hex(64)')}"
export QUEUE="$JUDGE0_VERSION"
export COUNT="${COUNT:-4}"
export INTERVAL="${INTERVAL:-0.1}"
exec "$@"
