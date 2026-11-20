#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
secret_directory=${1:-"$HOME/.local/share/techniview/secrets"}
helper_image=alpine:3.22

for name in mysql_root_password mysql_password email_signing_key resend_api_key; do
    if [[ ! -f "$secret_directory/$name" || ! -r "$secret_directory/$name" ]]; then
        echo "Missing or unreadable secret: $secret_directory/$name" >&2
        exit 1
    fi
done

docker image inspect "$helper_image" >/dev/null 2>&1 || docker pull "$helper_image"

copy_files() {
    local volume=$1 source_directory=$2
    shift 2
    docker volume create "$volume" >/dev/null
    tar -C "$source_directory" -cf - "$@" |
        docker run --rm -i --network none --mount "type=volume,src=$volume,dst=/target" \
            "$helper_image" sh -ec '
                mkdir /incoming
                tar -xf - -C /incoming
                if [ "$1" = secrets ]; then
                    for file in /incoming/*; do
                        target=/target/$(basename "$file")
                        if [ -e "$target" ] && ! cmp -s "$file" "$target"; then
                            echo "Refusing to replace an existing secret: $(basename "$file")" >&2
                            exit 1
                        fi
                    done
                fi
                cp -R /incoming/. /target/
                chown -R 0:0 /target
                find /target -type d -exec chmod 755 {} \;
                find /target -type f -exec chmod 444 {} \;
            ' sh "$copy_kind"
}

copy_kind=secrets
copy_files techniview_app_secrets "$secret_directory" mysql_password email_signing_key resend_api_key
copy_files techniview_database_secrets "$secret_directory" mysql_password mysql_root_password
copy_kind=config
copy_files techniview_prometheus_config "$repository_root/ops/monitoring" prometheus.yml
copy_files techniview_grafana_provisioning "$repository_root/ops/monitoring/grafana/provisioning" .
copy_files techniview_grafana_dashboards "$repository_root/ops/monitoring/grafana/dashboards" .
docker volume create techniview_captured_mail >/dev/null
docker run --rm --network none \
    --mount type=volume,src=techniview_captured_mail,dst=/target \
    "$helper_image" chown 10001:10001 /target
echo 'Docker volumes prepared.'
