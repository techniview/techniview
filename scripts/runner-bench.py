#!/usr/bin/env python3
"""Run sequential local bursts and retain evidence outside Compose volumes."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from runner_benchmark_support import prepare_pair, stop_reason

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "techniview-runner-bench"
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    "/dev/null",
    "-p",
    PROJECT,
    "-f",
    "compose.integration.yml",
    "-f",
    "compose.benchmark.yml",
]


def command(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0]) * 1024
    return {
        "available_bytes": values["MemAvailable"],
        "swap_used_bytes": values["SwapTotal"] - values["SwapFree"],
        "memory_pressure": Path("/proc/pressure/memory").read_text(),
        "vm_swap_counters": {
            key: int(value)
            for key, value in (
                line.split() for line in Path("/proc/vmstat").read_text().splitlines()
            )
            if key in {"pswpin", "pswpout", "pgmajfault"}
        },
    }


def host_diagnostics():
    def read(path):
        try:
            return path.read_text().strip()
        except OSError as error:
            return {"unavailable": str(error)}

    cpu_root = Path("/sys/devices/system/cpu")
    return {
        "cpu_frequency_khz": {
            path.parent.parent.name: read(path)
            for path in cpu_root.glob("cpu*/cpufreq/scaling_cur_freq")
        },
        "temperatures_millicelsius": {
            str(path): read(path)
            for path in Path("/sys/class/hwmon").glob("hwmon*/temp*_input")
        },
        "thermal_throttle_counts": {
            str(path): read(path)
            for path in cpu_root.glob("cpu*/thermal_throttle/*throttle_count")
        },
        "cpu_pressure": read(Path("/proc/pressure/cpu")),
        "io_pressure": read(Path("/proc/pressure/io")),
    }


def capture(args):
    return command(args, capture_output=True).stdout


def run_burst(
    directory, problem, concurrency, workers, source, warmup=False, direct_engine=None
):
    directory.mkdir(parents=True)
    (directory / "containers.json").write_text(
        capture(["docker", "inspect", *capture(COMPOSE + ["ps", "-q"]).split()])
    )
    log_since = datetime.now(UTC).isoformat()
    initial = memory()
    campaign_initial_swap = int(
        os.environ.get(
            "RUNNER_BENCH_CAMPAIGN_SWAP_BASELINE_BYTES",
            str(initial["swap_used_bytes"]),
        )
    )
    started = time.monotonic()
    reason = None
    container = f"{PROJECT}-burst"
    args = COMPOSE + [
        "run",
        "--rm",
        "--no-deps",
        "--name",
        container,
        "-e",
        f"LOAD_PROBLEM={problem}",
        "-e",
        f"LOAD_STUDENTS={concurrency}",
        "-e",
        f"LOAD_CONCURRENCY={concurrency}",
        "-e",
        "LOAD_APP_WORKERS=4",
        "-e",
        f"LOAD_JUDGE0_WORKERS={workers}",
        "-e",
        "LOAD_COMPLETION_TIMEOUT_SECONDS=300",
        "-e",
        f"LOAD_SOURCE_COMMIT={source}",
        "-e",
        f"ENGINE_BENCHMARK_ENGINE={direct_engine or 'isolate'}",
        "tests",
        "python",
        "-m",
        "performance.engine_benchmark" if direct_engine else "performance.load_test",
    ]
    with (
        (directory / "output.txt").open("w") as output,
        (directory / "resources.jsonl").open("w") as resources,
    ):
        process = subprocess.Popen(args, cwd=ROOT, stdout=output, stderr=output)
        stop_guard = threading.Event()
        guard_result = {}

        def guard_memory():
            low_since = None
            while not stop_guard.wait(0.25):
                try:
                    current = memory()
                except OSError as error:
                    guard_result["reason"] = f"Memory guard failed: {error}"
                    return
                reason, low_since = stop_reason(
                    campaign_initial_swap, current, time.monotonic(), low_since
                )
                if reason:
                    guard_result.update(
                        reason=reason,
                        sample=current,
                        burst_initial=initial,
                        campaign_initial_swap_used_bytes=campaign_initial_swap,
                        campaign_swap_growth_bytes=(
                            current["swap_used_bytes"] - campaign_initial_swap
                        ),
                        at=datetime.now(UTC).isoformat(),
                    )
                    (directory / "safety-stop.json").write_text(
                        json.dumps(guard_result, indent=2) + "\n"
                    )
                    subprocess.run(
                        ["docker", "stop", "-t", "1", container],
                        capture_output=True,
                        timeout=20,
                    )
                    return

        guard_thread = threading.Thread(target=guard_memory, daemon=True)
        guard_thread.start()
        try:
            while process.poll() is None:
                sample = memory()
                sample.update(host_diagnostics())
                sample["elapsed_seconds"] = time.monotonic() - started
                sample["at"] = datetime.now(UTC).isoformat()
                stats = subprocess.run(
                    [
                        "docker",
                        "stats",
                        "--no-stream",
                        "--format",
                        "{{json .}}",
                        *capture(COMPOSE + ["ps", "-q"]).split(),
                    ],
                    text=True,
                    capture_output=True,
                    timeout=15,
                )
                sample["docker_stats"] = stats.stdout.splitlines()
                sample["docker_stats_error"] = stats.stderr
                sample["cgroups"] = {}
                for container_id in capture(COMPOSE + ["ps", "-q"]).split():
                    group = (
                        Path("/sys/fs/cgroup/system.slice")
                        / f"docker-{container_id}.scope"
                    )
                    counters = {}
                    for name in (
                        "cpu.stat",
                        "memory.current",
                        "memory.events",
                        "memory.peak",
                        "memory.swap.current",
                        "memory.swap.events",
                    ):
                        try:
                            counters[name] = (group / name).read_text()
                        except OSError as error:
                            counters[name] = {"unavailable": str(error)}
                    sample["cgroups"][container_id] = counters
                resources.write(json.dumps(sample) + "\n")
                resources.flush()
                reason = guard_result.get("reason", reason)
                if time.monotonic() - started >= 330:
                    reason = (
                        "five-minute burst deadline plus preparation grace exceeded"
                    )
                if reason:
                    subprocess.run(
                        ["docker", "stop", "-t", "1", container],
                        capture_output=True,
                        timeout=20,
                    )
                    process.wait(timeout=30)
                    break
                time.sleep(0.5)
        except (OSError, subprocess.SubprocessError) as error:
            reason = f"Resource collection failed: {error}"
            subprocess.run(
                ["docker", "stop", "-t", "1", container],
                capture_output=True,
                timeout=20,
            )
            process.wait(timeout=30)
        finally:
            stop_guard.set()
            guard_thread.join(timeout=21)
            reason = guard_result.get("reason", reason)
    final_containers = json.loads(
        capture(["docker", "inspect", *capture(COMPOSE + ["ps", "-aq"]).split()])
    )
    (directory / "containers-final.json").write_text(
        json.dumps(final_containers, indent=2) + "\n"
    )
    failed_services = [
        item["Name"]
        for item in final_containers
        if item["State"].get("OOMKilled")
        or (
            not item["State"]["Running"]
            and item["Config"]["Labels"]["com.docker.compose.service"]
            not in {"callbacks", "go-judge"}
        )
    ]
    if failed_services and reason is None:
        reason = "Service stopped or OOM-killed: " + ", ".join(failed_services)
    report = {
        "complete": process.returncode == 0 and reason is None,
        "incomplete_reason": reason
        or ("test process failed" if process.returncode else None),
        "exit_code": process.returncode,
        "warmup": warmup,
        "workload": problem,
        "concurrency": concurrency,
        "runner_workers": workers,
        "runner_cpu_limit": int(os.environ.get("RUNNER_EXEC_CPU_LIMIT", "6")),
        "app_workers": 0 if direct_engine else 4,
        "direct_engine": direct_engine,
        "source_commit": source,
    }
    events = []
    for line in (directory / "output.txt").read_text().splitlines():
        if line.startswith('{"'):
            try:
                payload = json.loads(line)
            except ValueError:
                report.setdefault("output_parse_errors", []).append(line[:200])
                continue
            if "event" in payload:
                events.append(payload)
            else:
                report["measurements"] = payload
    (directory / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    (directory / "services.log").write_text(
        capture(COMPOSE + ["logs", "--no-color", "--since", log_since])
    )
    (directory / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["complete"]:
        raise RuntimeError(f"Incomplete burst: {directory}; reason={reason}")


def source_path(name):
    path = ROOT / name
    if name.startswith("benchmark-results/") or path.is_symlink():
        return None
    if any(
        part.startswith(".env") or part in {".aws", ".codex", ".agents"}
        for part in Path(name).parts
    ):
        return None
    return path if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--engine",
        choices=["isolate", "go-judge", "go-judge-shared"],
        default="isolate",
    )
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--http-reuse", action="store_true")
    parser.add_argument("--paired-http", action="store_true")
    parser.add_argument("--paired-outbox", action="store_true")
    parser.add_argument("--paired-dispatch", action="store_true")
    parser.add_argument("--paired-engine", action="store_true")
    parser.add_argument("--paired-engine-shared", action="store_true")
    parser.add_argument("--paired-engine-group-persistent", action="store_true")
    parser.add_argument(
        "--optimized-baseline",
        action="store_true",
        help="Give both paired engines grouping, persistent workers and HTTP reuse",
    )
    parser.add_argument("--paired-combined", action="store_true")
    parser.add_argument("--paired-group", action="store_true")
    parser.add_argument("--grouped", action="store_true")
    parser.add_argument("--paired-persistent", action="store_true")
    parser.add_argument("--paired-shared", action="store_true")
    parser.add_argument("--paired-group-persistent", action="store_true")
    parser.add_argument("--shared-python", action="store_true")
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument("--combined-ablation", action="store_true")
    parser.add_argument("--dispatch-concurrency", type=int, default=1)
    parser.add_argument("--callback-outbox", action="store_true")
    parser.add_argument("--problem", default="Ransom Note")
    parser.add_argument("--workers", type=int, choices=[8, 16, 24], default=8)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 10])
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.resume and (
        not (
            args.paired_combined
            or args.paired_group
            or args.paired_persistent
            or args.paired_shared
            or args.paired_group_persistent
            or args.paired_engine_group_persistent
        )
        or args.combined_ablation
    ):
        parser.error(
            "--resume supports paired combined, grouped, or persistent comparisons"
        )
    if args.grouped and (
        args.paired_group or args.paired_persistent or args.paired_shared
    ):
        parser.error(
            "select either an individual grouped profile or a paired comparison"
        )
    if args.persistent and not args.grouped:
        parser.error("--persistent requires --grouped")
    if args.shared_python and not args.grouped:
        parser.error("--shared-python requires --grouped")
    if args.paired_shared and args.engine not in {"isolate", "go-judge-shared"}:
        parser.error("paired shared execution requires isolate or go-judge-shared")
    if args.paired_group_persistent and args.engine != "go-judge-shared":
        parser.error("paired group-persistent execution requires go-judge-shared")
    if args.paired_engine_group_persistent and args.engine != "isolate":
        parser.error(
            "paired engine/group comparison selects its own engine profiles; "
            "omit --engine"
        )
    if args.combined_ablation and not args.paired_combined:
        parser.error("--combined-ablation requires --paired-combined")
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error(
            "label must contain only letters, numbers, hyphens and underscores"
        )
    if not all(1 <= c <= 25 for c in args.concurrency):
        parser.error("local concurrency must be between 1 and 25")
    if (
        sum(
            [
                args.paired_http,
                args.paired_outbox,
                args.paired_dispatch,
                args.paired_engine,
                args.paired_engine_shared,
                args.paired_combined,
                args.paired_group,
                args.paired_persistent,
                args.paired_shared,
                args.paired_group_persistent,
                args.paired_engine_group_persistent,
            ]
        )
        > 1
    ):
        parser.error("select one paired experiment")
    if not 1 <= args.dispatch_concurrency <= 32:
        parser.error("dispatch concurrency must be between 1 and 32")
    paired = any(
        [
            args.paired_http,
            args.paired_outbox,
            args.paired_dispatch,
            args.paired_engine,
            args.paired_engine_shared,
            args.paired_combined,
            args.paired_group,
            args.paired_persistent,
            args.paired_shared,
            args.paired_group_persistent,
            args.paired_engine_group_persistent,
        ]
    )
    if paired and (
        args.direct
        or (
            args.engine != "isolate"
            and not (
                (
                    args.paired_group
                    or args.paired_persistent
                    or args.paired_shared
                    or args.paired_group_persistent
                )
                and args.engine == "go-judge-shared"
            )
            and not (args.paired_http and args.engine == "go-judge-shared")
        )
        or args.http_reuse
        or args.callback_outbox
    ):
        parser.error("paired experiments require a baseline without combined features")
    if (
        paired
        and not (args.paired_dispatch or args.paired_combined)
        and args.dispatch_concurrency != 1
    ):
        parser.error(
            "dispatch concurrency changes require "
            "--paired-dispatch or --paired-combined"
        )
    if args.paired_dispatch and args.dispatch_concurrency == 1:
        parser.error("paired dispatch requires concurrency greater than one")
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    if args.direct and args.engine == "go-judge-shared":
        parser.error("direct comparison uses the standalone go-judge profile")
    if args.engine == "go-judge-shared":
        COMPOSE.extend(["-f", "compose.go-judge-shared.yml"])
    if args.engine == "go-judge":
        COMPOSE.extend(["-f", "compose.go-judge-experiment.yml"])
        if args.direct:
            COMPOSE.extend(["-f", "compose.go-judge-direct.yml"])
    if args.grouped or args.paired_persistent or args.paired_shared:
        COMPOSE.extend(["-f", "compose.group-experiment.yml"])
    if args.persistent or args.paired_persistent or args.paired_shared:
        COMPOSE.extend(["-f", "compose.persistent-workers.yml"])
    if args.shared_python or args.paired_shared:
        COMPOSE.extend(["-f", "compose.shared-python.yml"])
    directory = ROOT / "benchmark-results/local-runner" / args.label
    if args.resume and not (directory / "metadata.json").exists():
        parser.error("--resume requires an existing experiment with metadata")
    directory.mkdir(parents=True, exist_ok=args.resume)
    source = capture(["git", "rev-parse", "HEAD"]).strip()
    if args.optimized_baseline and not args.paired_engine_group_persistent:
        parser.error("--optimized-baseline requires --paired-engine-group-persistent")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    session_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    provenance = directory / "sessions" / session_id if args.resume else directory
    recovery = directory / "interrupted" / session_id
    previous = (
        json.loads((directory / "metadata.json").read_text()) if args.resume else None
    )
    if args.resume:
        if (
            bool(previous.get("optimized_baseline")) != args.optimized_baseline
            or previous["source_commit"] != source
            or bool(previous.get("paired_combined")) != args.paired_combined
            or bool(previous.get("paired_group")) != args.paired_group
            or bool(previous.get("paired_persistent")) != args.paired_persistent
            or bool(previous.get("paired_shared")) != args.paired_shared
            or bool(previous.get("paired_group_persistent"))
            != args.paired_group_persistent
            or bool(previous.get("paired_engine_group_persistent"))
            != args.paired_engine_group_persistent
            or previous.get("engine") != args.engine
            or previous["dispatch_concurrency"] != args.dispatch_concurrency
            or previous.get("runner_cpu_limit", 6)
            != int(os.environ.get("RUNNER_EXEC_CPU_LIMIT", "6"))
        ):
            parser.error(
                "resumed source commit/profile must match the original experiment"
            )
        for path in directory.glob("*/summary.json"):
            report = json.loads(path.read_text())
            if (
                report["workload"] != args.problem
                or report["runner_workers"] != args.workers
            ):
                parser.error(
                    "resumed workload and worker count must match existing results"
                )
    current_memory = memory()
    configured_campaign_swap = os.environ.get(
        "RUNNER_BENCH_CAMPAIGN_SWAP_BASELINE_BYTES"
    )
    if configured_campaign_swap is not None:
        campaign_initial_swap = int(configured_campaign_swap)
    elif (
        previous
        and previous.get("boot_id") == boot_id
        and "campaign_initial_swap_used_bytes" in previous
    ):
        campaign_initial_swap = previous["campaign_initial_swap_used_bytes"]
    else:
        campaign_initial_swap = current_memory["swap_used_bytes"]
    os.environ["RUNNER_BENCH_CAMPAIGN_SWAP_BASELINE_BYTES"] = str(campaign_initial_swap)
    provenance.mkdir(parents=True, exist_ok=True)
    metadata = {
        "resume": args.resume,
        "boot_id": boot_id,
        "problem": args.problem,
        "workers": args.workers,
        "runner_cpu_limit": int(os.environ.get("RUNNER_EXEC_CPU_LIMIT", "6")),
        "concurrency": args.concurrency,
        "repetitions": args.repetitions,
        "engine": args.engine,
        "direct": args.direct,
        "dispatch_concurrency": args.dispatch_concurrency,
        "paired_dispatch": args.paired_dispatch,
        "paired_engine": args.paired_engine,
        "paired_engine_shared": args.paired_engine_shared,
        "paired_combined": args.paired_combined,
        "paired_group": args.paired_group,
        "grouped": args.grouped,
        "paired_persistent": args.paired_persistent,
        "paired_shared": args.paired_shared,
        "paired_group_persistent": args.paired_group_persistent,
        "paired_engine_group_persistent": args.paired_engine_group_persistent,
        "optimized_baseline": args.optimized_baseline,
        "persistent": args.persistent,
        "combined_ablation": args.combined_ablation,
        "source_commit": source,
        "campaign_initial_swap_used_bytes": campaign_initial_swap,
        "previous_diff_sha256": (
            json.loads((directory / "metadata.json").read_text()).get("diff_sha256")
            if args.resume
            else None
        ),
        "diff_sha256": hashlib.sha256(capture(["git", "diff"]).encode()).hexdigest(),
        "started_at": datetime.now(UTC).isoformat(),
        "machine": platform.uname()._asdict(),
        "cpu": Path("/proc/cpuinfo").read_text(),
        "memory": current_memory,
        "docker_version": capture(["docker", "version"]),
        "compose_version": capture(["docker", "compose", "version"]),
        "http_reuse": args.http_reuse,
        "paired_http": args.paired_http,
        "paired_outbox": args.paired_outbox,
        "callback_outbox": args.callback_outbox,
        "service_limits": (ROOT / "compose.benchmark.yml").read_text(),
    }
    (provenance / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (provenance / "source.diff").write_text(capture(["git", "diff"]))
    source_files = capture(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    ).splitlines()
    manifest = {}
    untracked = {}
    for name in source_files:
        path = source_path(name)
        if path is not None:
            manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in capture(
        ["git", "ls-files", "--others", "--exclude-standard"]
    ).splitlines():
        path = source_path(name)
        if path is not None:
            try:
                untracked[name] = path.read_text()
            except UnicodeDecodeError:
                untracked[name] = {"binary_sha256": manifest[name]}
    (provenance / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    (provenance / "untracked-sources.json").write_text(
        json.dumps(untracked, indent=2) + "\n"
    )
    env = {
        **os.environ,
        "LOAD_JUDGE0_WORKERS": str(args.workers),
        "JUDGE0_REUSE_CONNECTIONS": (
            "1"
            if args.http_reuse or args.paired_group or args.paired_persistent
            else "0"
        ),
        "RUNNER_CALLBACK_OUTBOX": "1" if args.callback_outbox else "0",
        "WORKER_DISPATCH_CONCURRENCY": str(args.dispatch_concurrency),
        "RUNNER_EXECUTION_MODEL": "shared_python" if args.shared_python else "fresh",
    }
    try:
        command(
            COMPOSE
            + [
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "180",
                *([] if args.direct else ["--scale", "app_worker=4"]),
                *(
                    ["go-judge"]
                    if args.direct and args.engine == "go-judge"
                    else ["judge", "workers"]
                    if args.direct
                    else ["backend", "judge", "workers", "app_worker"]
                ),
            ],
            env=env,
        )
        readiness_url = (
            "http://go-judge:5050/version"
            if args.direct and args.engine == "go-judge"
            else "http://judge:2358/about"
        )
        readiness = (
            "import time,urllib.request\n"
            "for attempt in range(90):\n"
            " try:\n"
            f"  urllib.request.urlopen({readiness_url!r},timeout=2).read();break\n"
            " except OSError:\n"
            "  if attempt==89: raise\n"
            "  time.sleep(1)\n"
        )
        command(
            COMPOSE + ["run", "--rm", "--no-deps", "tests", "python", "-c", readiness]
        )
        (provenance / "containers.json").write_text(
            capture(["docker", "inspect", *capture(COMPOSE + ["ps", "-q"]).split()])
        )
        if args.direct:
            run_burst(
                directory / "warmup",
                args.problem,
                1,
                args.workers,
                source,
                True,
                args.engine,
            )
            for concurrency in args.concurrency:
                for repeat in range(1, args.repetitions + 1):
                    run_burst(
                        directory / f"c{concurrency}-r{repeat}",
                        args.problem,
                        concurrency,
                        args.workers,
                        source,
                        direct_engine=args.engine,
                    )
            return
        if args.callback_outbox:
            command(COMPOSE + ["up", "-d", "callbacks"], env=env)
        if (
            args.paired_http
            or args.paired_outbox
            or args.paired_dispatch
            or args.paired_engine
            or args.paired_engine_shared
            or args.paired_combined
            or args.paired_group
            or args.paired_persistent
            or args.paired_shared
            or args.paired_group_persistent
            or args.paired_engine_group_persistent
        ):
            base_compose = COMPOSE.copy()
            for concurrency in args.concurrency:
                for repeat in range(1, args.repetitions + 1):
                    candidate = (
                        "combined"
                        if args.paired_combined
                        else "grouped"
                        if args.paired_group
                        else "persistent"
                        if args.paired_persistent
                        else "shared-python"
                        if args.paired_shared
                        else "group-persistent"
                        if args.paired_group_persistent
                        else "go-judge-group-persistent"
                        if args.paired_engine_group_persistent
                        else "go-judge-shared"
                        if args.paired_engine_shared
                        else "go-judge"
                        if args.paired_engine
                        else "dispatch"
                        if args.paired_dispatch
                        else "outbox"
                        if args.paired_outbox
                        else "pooled"
                    )
                    prefix = f"c{concurrency}-r{repeat}"
                    if args.resume and prepare_pair(
                        directory, prefix, candidate, recovery
                    ):
                        print(f"Retaining complete pair: {prefix}", flush=True)
                        continue
                    variants = ("baseline", candidate)
                    if args.combined_ablation:
                        variants = ("baseline", "go-judge-shared", "combined")
                        offset = (repeat - 1) % len(variants)
                        variants = variants[offset:] + variants[:offset]
                    elif args.paired_shared:
                        variants = ("grouped", "shared-python")
                    elif args.paired_group_persistent:
                        variants = ("baseline", "group-persistent")
                    elif args.paired_engine_group_persistent and repeat % 2 == 0:
                        variants = tuple(reversed(variants))
                    elif (
                        args.paired_combined
                        or args.paired_http
                        or args.paired_group
                        or args.paired_persistent
                        or args.paired_group_persistent
                    ) and repeat % 2 == 0:
                        variants = tuple(reversed(variants))
                    for variant in variants:
                        pair_env = {
                            **env,
                            "JUDGE0_REUSE_CONNECTIONS": "1"
                            if variant in {"pooled", "combined"}
                            or args.paired_group
                            or args.paired_persistent
                            or args.paired_shared
                            or args.paired_group_persistent
                            or (
                                args.paired_engine_group_persistent
                                and (
                                    variant == "go-judge-group-persistent"
                                    or args.optimized_baseline
                                )
                            )
                            else "0",
                        }
                        if args.paired_group:
                            command(COMPOSE + ["stop", "judge", "workers"])
                            COMPOSE[:] = base_compose + (
                                ["-f", "compose.group-experiment.yml"]
                                if variant == "grouped"
                                else []
                            )
                            command(
                                COMPOSE
                                + ["up", "-d", "--force-recreate", "judge", "workers"],
                                env=pair_env,
                            )
                        if args.paired_persistent:
                            command(COMPOSE + ["stop", "workers"])
                            COMPOSE[:] = base_compose + (
                                ["-f", "compose.persistent-workers.yml"]
                                if variant == "persistent"
                                else []
                            )
                            command(
                                COMPOSE + ["up", "-d", "--force-recreate", "workers"],
                                env=pair_env,
                            )
                        if args.paired_shared:
                            pair_env["RUNNER_EXECUTION_MODEL"] = (
                                "shared_python"
                                if variant == "shared-python"
                                else "fresh"
                            )
                            command(
                                COMPOSE
                                + [
                                    "up",
                                    "-d",
                                    "--no-deps",
                                    "--force-recreate",
                                    "--scale",
                                    "app_worker=4",
                                    "app_worker",
                                ],
                                env=pair_env,
                            )
                        if args.paired_group_persistent:
                            command(COMPOSE + ["stop", "judge", "workers"])
                            COMPOSE[:] = base_compose + (
                                [
                                    "-f",
                                    "compose.group-experiment.yml",
                                    "-f",
                                    "compose.persistent-workers.yml",
                                ]
                                if variant == "group-persistent"
                                else []
                            )
                            pair_env["RUNNER_GROUP_PROFILE"] = (
                                "1" if variant == "group-persistent" else "0"
                            )
                            pair_env["JUDGE0_REUSE_CONNECTIONS"] = "1"
                            command(
                                COMPOSE
                                + ["up", "-d", "--force-recreate", "judge", "workers"],
                                env=pair_env,
                            )
                            command(
                                COMPOSE
                                + [
                                    "up",
                                    "-d",
                                    "--no-deps",
                                    "--force-recreate",
                                    "--scale",
                                    "app_worker=4",
                                    "app_worker",
                                ],
                                env=pair_env,
                            )
                        if args.paired_engine_group_persistent:
                            command(COMPOSE + ["stop", "judge", "workers"])
                            if variant == "go-judge-group-persistent":
                                COMPOSE[:] = base_compose + [
                                    "-f",
                                    "compose.go-judge-shared.yml",
                                    "-f",
                                    "compose.group-experiment.yml",
                                    "-f",
                                    "compose.persistent-workers.yml",
                                ]
                                pair_env["RUNNER_GROUP_PROFILE"] = "1"
                                pair_env["JUDGE0_REUSE_CONNECTIONS"] = "1"
                            else:
                                COMPOSE[:] = base_compose + (
                                    [
                                        "-f",
                                        "compose.group-experiment.yml",
                                        "-f",
                                        "compose.persistent-workers.yml",
                                    ]
                                    if args.optimized_baseline
                                    else []
                                )
                                if args.optimized_baseline:
                                    pair_env["RUNNER_GROUP_PROFILE"] = "1"
                                    pair_env["JUDGE0_REUSE_CONNECTIONS"] = "1"
                            command(
                                COMPOSE
                                + [
                                    "up",
                                    "-d",
                                    "--wait",
                                    "--wait-timeout",
                                    "180",
                                    "--force-recreate",
                                    "judge",
                                    "workers",
                                ],
                                env=pair_env,
                            )
                        if (
                            args.paired_engine
                            or args.paired_engine_shared
                            or args.paired_combined
                        ):
                            command(COMPOSE + ["stop", "workers"])
                            if (
                                variant == "baseline"
                                and "compose.go-judge-experiment.yml" in COMPOSE
                            ):
                                command(COMPOSE + ["stop", "go-judge"])
                            overlay = {
                                "go-judge": "compose.go-judge-experiment.yml",
                                "go-judge-shared": "compose.go-judge-shared.yml",
                                "combined": "compose.go-judge-shared.yml",
                            }.get(variant)
                            COMPOSE[:] = base_compose + (
                                ["-f", overlay] if overlay else []
                            )
                            command(
                                COMPOSE + ["up", "-d", "--force-recreate", "workers"],
                                env=pair_env,
                            )
                        if args.paired_dispatch or args.paired_combined:
                            pair_env["WORKER_DISPATCH_CONCURRENCY"] = (
                                str(args.dispatch_concurrency)
                                if variant in {"dispatch", "combined"}
                                else "1"
                            )
                        if args.paired_outbox:
                            pair_env["JUDGE0_REUSE_CONNECTIONS"] = "0"
                            pair_env["RUNNER_CALLBACK_OUTBOX"] = (
                                "1" if variant == "outbox" else "0"
                            )
                            if variant == "baseline":
                                command(COMPOSE + ["stop", "callbacks"])
                            command(
                                COMPOSE
                                + [
                                    "up",
                                    "-d",
                                    "--no-deps",
                                    "--force-recreate",
                                    "workers",
                                ],
                                env=pair_env,
                            )
                            if variant == "outbox":
                                command(
                                    COMPOSE + ["up", "-d", "callbacks"], env=pair_env
                                )
                        command(
                            COMPOSE
                            + [
                                "up",
                                "-d",
                                "--no-deps",
                                "--force-recreate",
                                "--scale",
                                "app_worker=4",
                                "app_worker",
                            ],
                            env=pair_env,
                        )
                        prefix = f"c{concurrency}-r{repeat}-{variant}"
                        run_burst(
                            directory / f"{prefix}-warmup",
                            args.problem,
                            concurrency
                            if args.paired_group
                            or args.paired_persistent
                            or args.paired_shared
                            or args.paired_group_persistent
                            or args.paired_engine_group_persistent
                            else 1,
                            args.workers,
                            source,
                            True,
                        )
                        run_burst(
                            directory / prefix,
                            args.problem,
                            concurrency,
                            args.workers,
                            source,
                        )
        else:
            run_burst(directory / "warmup", args.problem, 1, args.workers, source, True)
            for concurrency in args.concurrency:
                for repeat in range(1, args.repetitions + 1):
                    run_burst(
                        directory / f"c{concurrency}-r{repeat}",
                        args.problem,
                        concurrency,
                        args.workers,
                        source,
                    )
    finally:
        try:
            try:
                if args.direct:
                    (directory / "database-state.json").write_text(
                        json.dumps({"not_applicable": "direct execution"}) + "\n"
                    )
                else:
                    snapshot = subprocess.run(
                        COMPOSE
                        + [
                            "run",
                            "--rm",
                            "--no-deps",
                            "tests",
                            "python",
                            "-m",
                            "performance.snapshot",
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        timeout=30,
                    )
                    (directory / "database-state.json").write_text(snapshot.stdout)
                    (directory / "database-state-errors.txt").write_text(
                        snapshot.stderr
                    )
            except (OSError, subprocess.SubprocessError) as error:
                (directory / "database-state-errors.txt").write_text(str(error))
            (directory / "services.log").write_text(
                capture(COMPOSE + ["logs", "--no-color"])
            )
        finally:
            command(
                COMPOSE
                + [
                    "--profile",
                    "callback-outbox",
                    "down",
                    "--volumes",
                    "--remove-orphans",
                ]
            )


if __name__ == "__main__":
    main()
