#!/bin/sh
set -eu

# Docker's private cgroup namespace restricts these operations to this container.
root=/sys/fs/cgroup
[ -f "$root/cgroup.controllers" ] || {
    echo "Runner requires Linux cgroup v2 and a private cgroup namespace." >&2
    exit 1
}
[ "$(wc -l < /proc/self/cgroup)" -eq 1 ]
grep -qx '0::/' /proc/self/cgroup || {
    echo "Runner requires a private cgroup namespace; host cgroups are unsupported." >&2
    exit 1
}
mkdir -p "$root/manager"
printf '%s\n' "$$" > "$root/manager/cgroup.procs"
# init:true also places tini in the container; move it before enabling controllers.
while read -r pid; do
    [ -z "$pid" ] || printf '%s\n' "$pid" > "$root/manager/cgroup.procs"
done < "$root/cgroup.procs"
printf '%s\n' '+cpu +memory +pids' > "$root/cgroup.subtree_control"
mkdir -p "$root/sandboxes" /run/isolate/locks /run/isolate/slots
printf '%s\n' '+cpu +memory +pids' > "$root/sandboxes/cgroup.subtree_control"
printf '%s\n' "$root/sandboxes" > /run/isolate/cgroup
chown judge0:judge0 /run/isolate/slots
export HOME=/home/judge0
exec setpriv --reuid=judge0 --regid=judge0 --init-groups /api/docker-entrypoint.sh "$@"
