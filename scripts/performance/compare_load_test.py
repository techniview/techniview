#!/usr/bin/env python3
"""Compare base and proposed backend revisions on one Docker host."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from performance.comparison import (
    append_measured_result,
    workload_overlay,
    write_json,
)
from performance.regression import compare_reports

WORKLOADS = ("short", "cpu-heavy", "multi-case")
MEASURED_RUNS = 3


def run(command: list[str], *, env: dict[str, str], check: bool = True) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
        )
    return result.stdout


def host_profile() -> dict[str, object]:
    memory = {}
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                key, value, _unit = line.split()
                memory[key.removesuffix(":")] = int(value) * 1024
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "memory_bytes": memory,
        "runner_name": os.getenv("RUNNER_NAME", "local"),
        "runner_os": os.getenv("RUNNER_OS", platform.system()),
        "runner_arch": os.getenv("RUNNER_ARCH", platform.machine()),
    }


def compose_prefix(repo: Path, overlay: Path, project: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "--project-name",
        project,
        "--file",
        str(repo / "compose.integration.yml"),
        "--file",
        str(overlay),
    ]


def image_id(prefix: list[str], service: str, env: dict[str, str]) -> str:
    container = run([*prefix, "ps", "--quiet", service], env=env).splitlines()[0]
    if not container:
        raise RuntimeError(f"No running container for {service}")
    return run(
        ["docker", "inspect", "--format", "{{.Image}}", container], env=env
    ).strip()


def image_revision(image: str, env: dict[str, str]) -> str:
    return run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            '{{ index .Config.Labels "org.opencontainers.image.revision" }}',
            image,
        ],
        env=env,
    ).strip()


def report_from_output(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "completion_batch_seconds" in value:
            return value
    raise RuntimeError("Load test finished without a JSON benchmark report")


def run_once(
    prefix: list[str],
    *,
    workload: str,
    label: str,
    students: int,
    concurrency: int,
    app_workers: int,
    worker_processes: int,
    judge_slots: int,
    source_commit: str,
    host: dict[str, object],
    env: dict[str, str],
) -> dict[str, object]:
    child_env = env | {
        "GO_JUDGE_PARALLELISM": str(judge_slots),
        "DIRECT_WORKER_PROCESSES": str(worker_processes),
    }
    image_backend = image_id(prefix, "backend", child_env)
    image_worker = image_id(prefix, "app_worker", child_env)
    image_runner = image_id(prefix, "go-judge", child_env)
    for service_image in (image_backend, image_worker):
        if image_revision(service_image, child_env) != source_commit:
            raise RuntimeError(
                f"{label} {service_image} does not identify revision {source_commit}"
            )
    command = [
        *prefix,
        "run",
        "--rm",
        "--no-deps",
        "--env",
        f"LOAD_STUDENTS={students}",
        "--env",
        f"LOAD_CONCURRENCY={concurrency}",
        "--env",
        f"LOAD_APP_WORKERS={app_workers}",
        "--env",
        f"LOAD_GO_JUDGE_SLOTS={judge_slots}",
        "--env",
        f"DIRECT_WORKER_PROCESSES={worker_processes}",
        "--env",
        f"LOAD_WORKLOAD={workload}",
        "--env",
        f"LOAD_SOURCE_COMMIT={source_commit}",
        "--env",
        f"LOAD_BACKEND_IMAGE_ID={image_backend}",
        "--env",
        f"LOAD_WORKER_IMAGE_ID={image_worker}",
        "--env",
        f"LOAD_APPLICATION_IMAGE_REVISION={source_commit}",
        "--env",
        f"LOAD_RUNNER_IMAGE_ID={image_runner}",
        "--env",
        f"LOAD_RUNNER_CPU_LIMIT={env['RUNNER_CPU_LIMIT']}",
        "--env",
        f"LOAD_RUNNER_MEMORY_LIMIT={env['RUNNER_MEMORY_LIMIT']}",
        "--env",
        f"LOAD_API_DB_POOL_SIZE={env['LOAD_API_DB_POOL_SIZE']}",
        "--env",
        f"LOAD_WORKER_DB_POOL_SIZE={env['LOAD_WORKER_DB_POOL_SIZE']}",
        "--env",
        f"LOAD_DB_MAX_OVERFLOW={env['LOAD_DB_MAX_OVERFLOW']}",
        "--env",
        f"LOAD_HOST_PROFILE_JSON={json.dumps(host, sort_keys=True)}",
        "--env",
        f"LOAD_REPORT_RUN={label}",
        "tests",
        "python",
        "-m",
        "performance.load_test",
    ]
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, env=child_env
    )
    if result.returncode:
        raise RuntimeError(
            f"{label} {workload} load failed ({result.returncode})\n"
            f"{result.stdout[-6000:]}\n{result.stderr[-6000:]}"
        )
    report = report_from_output(result.stdout)
    report["comparison_revision"] = label
    report["source_commit"] = source_commit
    report["backend_build_context"] = env["PERF_APPLICATION_BACKEND_CONTEXT"]
    report["worker_build_context"] = env["PERF_APPLICATION_BACKEND_CONTEXT"]
    report["test_build_context"] = env["PERF_TEST_BACKEND_CONTEXT"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--proposed-commit", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--students", type=int, default=100)
    parser.add_argument("--app-workers", type=int, default=4)
    parser.add_argument("--worker-processes", type=int, default=1)
    parser.add_argument("--judge-slots", type=int, default=4)
    parser.add_argument("--runner-cpu-limit", default="4")
    parser.add_argument("--runner-memory-limit", default="8g")
    parser.add_argument("--api-db-pool-size", type=int, default=30)
    parser.add_argument("--worker-db-pool-size", type=int, default=3)
    parser.add_argument("--db-max-overflow", type=int, default=0)
    parser.add_argument("--go-judge-wall-seconds", type=int, default=30)
    parser.add_argument("--warmup-students", type=int, default=5)
    parser.add_argument(
        "--workloads", nargs="+", choices=WORKLOADS, default=list(WORKLOADS)
    )
    parser.add_argument("--measured-runs", type=int, default=MEASURED_RUNS)
    args = parser.parse_args()
    if args.measured_runs < 1 or args.warmup_students < 1 or args.students < 1:
        parser.error("students, warmup-students, and measured-runs must be positive")
    if not 0 < args.go_judge_wall_seconds < 40:
        parser.error("go-judge wall limit must fit below the 60-second worker lease")

    head = Path(__file__).resolve().parents[2]
    base = args.base_path.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    host = host_profile()
    env = os.environ.copy()
    env["COMPOSE_INTERACTIVE_NO_CLI"] = "1"
    summary: dict[str, object] = {
        "base_commit": args.base_commit,
        "proposed_commit": args.proposed_commit,
        "host_profile": host,
        "measured_runs_per_workload": args.measured_runs,
        "workload_version": 1,
        "workloads": {},
    }
    if args.base_commit == args.proposed_commit:
        summary["status"] = "skipped"
        summary["skip_reason"] = (
            "Base and proposed commits are identical; no revision comparison is needed."
        )
        summary["failures"] = []
        summary_path = args.output_dir / "comparison.json"
        write_json(summary_path, summary)
        print(summary_path.read_text())
        return 0

    failures = []

    with tempfile.TemporaryDirectory(prefix="techniview-perf-") as temp_dir:
        run_id = os.getenv("GITHUB_RUN_ID", uuid4().hex[:10])
        for revision, commit in (
            ("base", args.base_commit),
            ("proposed", args.proposed_commit),
        ):
            application_backend = (base if revision == "base" else head) / "backend"
            overlay = Path(temp_dir) / f"compose.performance.{revision}.yml"
            overlay.write_text(
                workload_overlay(application_backend, head / "backend", commit),
                encoding="utf-8",
            )
            for workload in args.workloads:
                project = re.sub(
                    r"[^a-z0-9]",
                    "",
                    f"tvperf{run_id}{revision}{workload}",
                )[:55]
                prefix = compose_prefix(head, overlay, project)
                project_env = env | {
                    "GO_JUDGE_PARALLELISM": str(args.judge_slots),
                    "DIRECT_WORKER_PROCESSES": str(args.worker_processes),
                    "RUNNER_CPU_LIMIT": args.runner_cpu_limit,
                    "RUNNER_MEMORY_LIMIT": args.runner_memory_limit,
                    "LOAD_API_DB_POOL_SIZE": str(args.api_db_pool_size),
                    "LOAD_WORKER_DB_POOL_SIZE": str(args.worker_db_pool_size),
                    "LOAD_DB_MAX_OVERFLOW": str(args.db_max_overflow),
                    "LOAD_GO_JUDGE_WALL_SECONDS": str(args.go_judge_wall_seconds),
                    "PERF_APPLICATION_BACKEND_CONTEXT": str(application_backend),
                    "PERF_TEST_BACKEND_CONTEXT": str(head / "backend"),
                }
                workload_record: dict[str, object] = {
                    "revision": revision,
                    "commit": commit,
                    "workload": workload,
                    "warmup": None,
                    "measured": [],
                    "error": None,
                }
                output_path = args.output_dir / f"{revision}-{workload}.json"
                write_json(output_path, workload_record)
                try:
                    run(
                        [
                            *prefix,
                            "up",
                            "--detach",
                            "--build",
                            "--wait",
                            "--scale",
                            f"app_worker={args.app_workers}",
                            "backend",
                            "go-judge",
                            "app_worker",
                        ],
                        env=project_env,
                    )
                    workload_record["warmup"] = run_once(
                        prefix,
                        workload=workload,
                        label="warmup",
                        students=args.warmup_students,
                        concurrency=args.warmup_students,
                        app_workers=args.app_workers,
                        worker_processes=args.worker_processes,
                        judge_slots=args.judge_slots,
                        source_commit=commit,
                        host=host,
                        env=project_env,
                    )
                    write_json(output_path, workload_record)
                    for index in range(1, args.measured_runs + 1):
                        measured = run_once(
                            prefix,
                            workload=workload,
                            label=f"measured-{index}",
                            students=args.students,
                            concurrency=args.students,
                            app_workers=args.app_workers,
                            worker_processes=args.worker_processes,
                            judge_slots=args.judge_slots,
                            source_commit=commit,
                            host=host,
                            env=project_env,
                        )
                        append_measured_result(workload_record, measured, output_path)
                # Preserve partial evidence for CI artifacts on benchmark errors.
                except Exception as error:
                    workload_record["error"] = str(error)
                    failures.append(f"{revision}/{workload}: {error}")
                    workload_record["compose_logs"] = subprocess.run(
                        [*prefix, "logs", "--tail=100", "backend", "app_worker"],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=project_env,
                    ).stdout[-12000:]
                finally:
                    subprocess.run(
                        [*prefix, "down", "--volumes", "--remove-orphans"],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=project_env,
                    )
                write_json(output_path, workload_record)
                summary["workloads"][f"{revision}/{workload}"] = {
                    "artifact": output_path.name,
                    "error": workload_record["error"],
                }

    if not failures:
        for workload in args.workloads:
            base_record = json.loads(
                (args.output_dir / f"base-{workload}.json").read_text()
            )
            proposed_record = json.loads(
                (args.output_dir / f"proposed-{workload}.json").read_text()
            )
            base_backend_image = base_record["warmup"]["backend_image_id"]
            proposed_backend_image = proposed_record["warmup"]["backend_image_id"]
            base_worker_image = base_record["warmup"]["worker_image_id"]
            proposed_worker_image = proposed_record["warmup"]["worker_image_id"]
            if base_backend_image == proposed_backend_image:
                failures.append(
                    f"{workload} reused one backend image for both revisions"
                )
            if base_worker_image == proposed_worker_image:
                failures.append(
                    f"{workload} reused one worker image for both revisions"
                )
            comparison = compare_reports(
                base_record["measured"], proposed_record["measured"]
            )
            comparison["base_backend_image_id"] = base_backend_image
            comparison["proposed_backend_image_id"] = proposed_backend_image
            comparison["base_worker_image_id"] = base_worker_image
            comparison["proposed_worker_image_id"] = proposed_worker_image
            summary["workloads"][workload] = comparison
            if comparison["regression_gate_failed"]:
                failures.append(
                    f"{workload} exceeded both regression thresholds: "
                    f"{comparison['delta_seconds']:.3f}s and "
                    f"{comparison['ratio']:.3f}x"
                )
    summary["no_cross_workload_score"] = True
    summary["failures"] = failures
    summary_path = args.output_dir / "comparison.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(summary_path.read_text())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
