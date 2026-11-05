# Runner decision and evidence

Production uses standalone go-judge 1.13.3 with Python 3.14.8. The application
owns durable submission and case attempts in MySQL, grades the returned output,
and marks interrupted attempts as unknown. go-judge owns sandbox execution only.
The runner image pins the Debian base by digest and installs build and runtime
packages from a fixed Debian snapshot. The Python source archive and go-judge
binary are checksum-verified. The runtime keeps Python's OpenSSL library and CA
bundle without the unused `openssl` command-line package.

The earlier Judge0 fork, grouped Ruby workers, PostgreSQL, and Redis were part of
the hybrid experiment. They are no longer built or deployed. The A100 comparison
and local direct integration tests informed this migration; historical hybrid
figures are preserved in benchmark artifacts. The direct path has passed the
real sandbox and application integration suite, including CPU, memory, output,
filesystem isolation, result persistence, and worker restart recovery. A hosted
100-concurrent submission capacity result is still needed before making a campus
throughput claim.

## Verified runner controls

The go-judge image starts with `-no-fallback` and
`-container-cred-start 1536`, as described in the [pinned go-judge
configuration](https://github.com/criyle/go-judge/blob/v1.13.3/README.md). The
mount YAML `uid: 1536` describes the sandbox mount configuration; by itself it
does not change the execution credentials.
Without `-container-cred-start`, go-judge uses its default unprivileged root
identity. The integration probe now checks the credentials directly. It observed
UID 1536, GID 1536, and `CapEff` zero in student code.

The pinned go-judge build reports cgroup v2 with the CPU, cpuset, memory, and pids
controllers. Real integration cases passed CPU timeout and strict memory-limit
checks with `-no-fallback` enabled. The probe also tried to read `/etc/shadow`,
`/root/.ssh/authorized_keys`, `/proc/1/environ`, `/proc/1/root/etc/shadow`, and
`/sys/fs/cgroup/cgroup.procs`. None were readable. `/proc/1/cmdline` showed
`/proc/self/exe container_init`, the sandbox's own init process. Before running
the student probe, a helper inside the runner container resolved backend, MySQL,
and a network peer on a separate bridge to numeric addresses and connected to
each one successfully. The sandbox then failed to connect to those same
addresses and to the runner's loopback API. This checks the network namespace
without relying on an internet endpoint. The probe found no Docker socket. A
sentinel environment variable set only on the runner container was absent from
the student process.

## Runner image lifecycle

The image is not built from source on every CI run.
The `Bake runner image` workflow is a manual dispatch that builds the image from
the pinned Dockerfile, pushes it to GitHub Container Registry as
`go-judge:runner-<runnumber>` plus a rolling `go-judge:runner-latest` tag,
pulls and verifies the published image, then reports its digest for a reviewed
PR updating `go-judge/runner-image.ref`. CI requires that image and fails if
it cannot pull it. Local `make integration` and `make up` fall back to a source
build when the pull fails. The runner VM consumes the same digest
ref through `GO_JUDGE_IMAGE`. PRs that change the image recipe or the CI
build scripts still build and verify all production images from source in the
`Production image builds` check.

Because snapshot.debian.org throttles heavy fetches, the image build retries
`apt-get update` and `apt-get install` against the pinned snapshot with
exponential backoff and treats partial index downloads as failures; the retry
helper streams output to a log file instead of buffering it in memory.

The sandbox uses go-judge's built-in Moby seccomp filter. Its `/config` response
reported `seccomp: true`. Its filesystem contains only the configured read-only
library and Python binds, `/dev/null`, `/dev/urandom`, temporary filesystems for
`/w` and `/tmp`, and a proc mount. The runner service has a read-only root
filesystem and a tmpfs at `/tmp`; go-judge needs that tmpfs to create its
transient mount tree. The service also sets `no-new-privileges:true`.

The production Compose project contains only go-judge, on its own default Docker
bridge. It does not attach the runner to an app Compose network. The API port
binds to `RUNNER_PRIVATE_BIND_IP`; the application VM must reach it through that
private address. Docker uses its default private PID namespace because Compose
does not accept `private` as a `pid` value. The runner API is unauthenticated,
so the campus firewall must allow port 5050 only from the application VM. The
service network still has outbound access. An `internal: true` network and a
bridge with IP masquerading disabled both prevented the host-published API from
answering in the local Docker trial, so neither is configured. The integration
stack uses the normal default bridge and a second bridge for the network peer.
The runner parent reached services on both bridges; sandboxed code could not
reach the numeric peer addresses on either one.

## Privileged mode and limits of this check

The runner container remains privileged. Docker documents that privileged mode
grants all capabilities and disables its default seccomp profile ([Docker run
reference](https://docs.docker.com/reference/cli/docker/container/run/)). A
trial with `privileged: false` exited at startup because go-judge could not
create `/sys/fs/cgroup/init` on the read-only cgroup mount. `-no-fallback`
stopped the service instead of silently running without cgroup enforcement. A
`cap_drop: [ALL]` trial with selected capabilities also left the privileged
process with `CapEff: 000001ffffffffff`; Docker grants all capabilities in
privileged mode. No custom Docker seccomp profile is installed. Docker disables
its default seccomp profile for privileged containers, and a custom profile was
not validated with the required cgroup access. The embedded go-judge seccomp
filter for student jobs is enabled and was confirmed separately.

The integration checks ran on the available local Docker host, whose runner log
reported Linux kernel 7.2 and cgroup v2. The target runner VM was not available in
this task. Before accepting submissions there, run the full integration suite on
that VM and confirm the API remains reachable only from the application VM, the
CPU and memory cases still fail at their limits, and runner restart recovery
passes. The target VM must use a patched Linux kernel with cgroup v2 and remain
dedicated to untrusted code. These local results do not establish the target
VM's Docker configuration or firewall rules.
