#!/usr/bin/env python3
"""Run a guarded, resumable Judge0 versus go-judge API comparison."""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from runner_benchmark_support import stop_reason

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark-results/local-runner"
PROJECT = "techniview-runner-bench"
BASE_COMPOSE = [
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
GO_JUDGE_COMPOSE = BASE_COMPOSE + ["-f", "compose.go-judge-experiment.yml"]
GROUP_PERSISTENT_COMPOSE = BASE_COMPOSE + [
    "-f",
    "compose.go-judge-shared.yml",
    "-f",
    "compose.group-experiment.yml",
    "-f",
    "compose.persistent-workers.yml",
]
PROBLEMS = (
    "Ransom Note",
    "Number of Islands",
    "Minimum Cost for Tickets",
)


def now():
    return datetime.now(UTC).isoformat()


def memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0]) * 1024
    return {
        "available_bytes": values["MemAvailable"],
        "swap_used_bytes": values["SwapTotal"] - values["SwapFree"],
    }


def write_state(path, state):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(path)


def cell_label(prefix, problem, workers=None, cpu_limit=None):
    slug = problem.lower().replace(" ", "-")
    suffix = ""
    if cpu_limit is not None:
        suffix += f"-cpu{cpu_limit}"
    if workers is not None:
        suffix += f"-w{workers}"
    return f"{prefix}-{slug}{suffix}"


def report(campaign_dir, state):
    profile = state.get("profile", "engine-only")
    candidate = (
        "go-judge-group-persistent" if profile == "group-persistent" else "go-judge"
    )
    profile_description = (
        "Candidate: grouped jobs, persistent Ruby workers, pooled HTTP, "
        "fresh Python per case."
        if profile == "group-persistent"
        else "Grouping, persistent workers, and HTTP reuse are disabled."
    )
    worker_counts = state.get("worker_counts", [8])
    cpu_limits = state.get("cpu_limits", [6])
    matrix_dimensions = len(worker_counts) > 1 or len(cpu_limits) > 1
    worker_description = ", ".join(str(count) for count in worker_counts)
    cpu_description = ", ".join(str(count) for count in cpu_limits)
    lines = [
        f"# Judge0 versus go-judge campaign: {state['label']}",
        "",
        f"Status: **{state['status']}**",
        "",
        f"Source commit: `{state['source_commit']}`",
        "",
        f"Runner CPU budgets: {cpu_description}; worker counts: {worker_description}.",
        "Other limits: 4 app workers, 8 GiB runner memory.",
        "Both profiles use fresh Python state per case.",
        profile_description,
        "",
        f"Candidate profile: `{candidate}`",
        "",
        f"Profile checks: {state.get('verification_status', 'not required')}",
        "",
        "| Workload | Status | Comparison |",
        "| --- | --- | --- |",
    ]
    for cpu_limit in cpu_limits:
        for workers in worker_counts:
            for problem in PROBLEMS:
                name = cell_label(
                    state["label"],
                    problem,
                    workers if matrix_dimensions else None,
                    cpu_limit if matrix_dimensions else None,
                )
                cell = state["cells"].get(name, {})
                link = (
                    f"[comparison](../{cell['result_label']}/comparison.md)"
                    if cell.get("status") == "complete"
                    else "—"
                )
                workload = (
                    f"{problem} ({cpu_limit} CPUs, {workers} workers)"
                    if matrix_dimensions
                    else problem
                )
                lines.append(
                    f"| {workload} | {cell.get('status', 'pending')} | {link} |"
                )
    if state.get("safety_stopped"):
        lines.extend(["", "The campaign stopped at a host safety limit."])
    (campaign_dir / "REPORT.md").write_text("\n".join(lines) + "\n")


def safety_check(initial_swap, initial_low_memory=False):
    low_since = time.monotonic() if initial_low_memory else None
    while low_since is not None:
        current = memory()
        reason, low_since = stop_reason(
            initial_swap, current, time.monotonic(), low_since
        )
        if reason:
            return reason, current
        if low_since is None:
            break
        time.sleep(0.25)
    current = memory()
    reason, _ = stop_reason(initial_swap, current, time.monotonic(), None)
    return (reason, current) if reason else None


def stop_campaign(campaign_dir, state_path, state, reason, sample):
    (campaign_dir / "safety-stop.json").write_text(
        json.dumps(
            {
                "reason": reason,
                "at": now(),
                "initial_swap_used_bytes": state["initial_swap_used_bytes"],
                "swap_growth_bytes": sample["swap_used_bytes"]
                - state["initial_swap_used_bytes"],
                "sample": sample,
            },
            indent=2,
        )
        + "\n"
    )
    state["status"] = "safety_stopped"
    state["safety_stopped"] = True
    state["updated_at"] = now()
    write_state(state_path, state)
    report(campaign_dir, state)


def current_commit():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Unique campaign label")
    parser.add_argument(
        "--profile",
        choices=["engine-only", "group-persistent"],
        default="engine-only",
        help="Compare the engine alone or the complete grouped-worker candidate",
    )
    parser.add_argument(
        "--workers",
        type=int,
        choices=[8, 16, 24],
        nargs="+",
        default=[8],
        help="Runner worker counts to compare",
    )
    parser.add_argument(
        "--cpu-limits",
        type=int,
        choices=[6, 24],
        nargs="+",
        default=[6],
        help="Runner CPU quotas to compare while keeping memory fixed at 8 GiB",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error(
            "label must contain only letters, numbers, hyphens, and underscores"
        )
    if len(set(args.workers)) != len(args.workers):
        parser.error("worker counts must be unique")
    if len(set(args.cpu_limits)) != len(args.cpu_limits):
        parser.error("CPU limits must be unique")

    campaign_dir = RESULTS / f"{args.label}-campaign"
    state_path = campaign_dir / "campaign.json"
    commit = current_commit()
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    host_memory = memory()
    if args.resume:
        if not state_path.exists():
            parser.error("--resume requires an existing campaign manifest")
        state = json.loads(state_path.read_text())
        if state["source_commit"] != commit:
            parser.error("source commit changed; start a new campaign label")
        if state.get("profile", "engine-only") != args.profile:
            parser.error("campaign profile changed; start a new campaign label")
        if state.get("worker_counts", [8]) != args.workers:
            parser.error("worker counts changed; start a new campaign label")
        if state.get("cpu_limits", [6]) != args.cpu_limits:
            parser.error("CPU limits changed; start a new campaign label")
        if state["boot_id"] != boot_id:
            state.setdefault("sessions", []).append(
                {
                    "boot_id": boot_id,
                    "started_at": now(),
                    "initial_memory": host_memory,
                    "reason": "new host boot; reset swap safety baseline",
                }
            )
            state["boot_id"] = boot_id
            state["initial_swap_used_bytes"] = host_memory["swap_used_bytes"]
            state["safety_stopped"] = False
        elif state.get("safety_stopped"):
            parser.error("campaign safety-stopped on this boot; wait for host recovery")
    else:
        if campaign_dir.exists():
            parser.error("campaign exists; use --resume or choose another label")
        campaign_dir.mkdir(parents=True)
        state = {
            "version": 1,
            "label": args.label,
            "profile": args.profile,
            "worker_counts": args.workers,
            "cpu_limits": args.cpu_limits,
            "status": "running",
            "source_commit": commit,
            "boot_id": boot_id,
            "started_at": now(),
            "initial_swap_used_bytes": host_memory["swap_used_bytes"],
            "initial_memory": host_memory,
            "machine": platform.uname()._asdict(),
            "cpu": Path("/proc/cpuinfo").read_text(),
            "cells": {},
            "sessions": [],
        }

    if state.get("safety_stopped"):
        parser.error("campaign is safety-stopped; do not resume on this host boot")

    # Refuse to interfere with any containers already using this dedicated project.
    running = subprocess.run(
        BASE_COMPOSE + ["ps", "--status", "running", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if running:
        parser.error(
            f"Compose project {PROJECT} already has running containers; "
            "inspect them before starting"
        )

    state["updated_at"] = now()
    write_state(state_path, state)
    report(campaign_dir, state)

    guard = safety_check(
        state["initial_swap_used_bytes"],
        host_memory["available_bytes"] < 2 * 1024**3,
    )
    if guard:
        stop_campaign(campaign_dir, state_path, state, *guard)
        print("Host safety stop before build", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["RUNNER_BENCH_CAMPAIGN_SWAP_BASELINE_BYTES"] = str(
        state["initial_swap_used_bytes"]
    )
    environment["RUNNER_EXEC_CPU_LIMIT"] = str(args.cpu_limits[0])

    if args.profile == "group-persistent" and not state.get("verification_finished_at"):
        state["verification_status"] = "running"
        state["updated_at"] = now()
        write_state(state_path, state)
        report(campaign_dir, state)
        print("Running grouped go-judge integration and sandbox checks", flush=True)
        verified = subprocess.run(
            ["bash", "scripts/verify-runner-candidate.sh", "go-judge-group-persistent"],
            cwd=ROOT,
            env=environment,
        )
        if verified.returncode == 0:
            verified = subprocess.run(
                ["bash", "scripts/verify-go-judge-worker-restart.sh"],
                cwd=ROOT,
                env=environment,
            )
        if verified.returncode:
            state["status"] = "verification_failed"
            state["verification_status"] = "failed"
            state["verification_exit_code"] = verified.returncode
            state["updated_at"] = now()
            write_state(state_path, state)
            report(campaign_dir, state)
            return verified.returncode
        state["verification_finished_at"] = now()
        state["verification_status"] = "complete"
        write_state(state_path, state)
        report(campaign_dir, state)

        guard = safety_check(
            state["initial_swap_used_bytes"],
            memory()["available_bytes"] < 2 * 1024**3,
        )
        if guard:
            stop_campaign(campaign_dir, state_path, state, *guard)
            print("Host safety stop after profile verification", file=sys.stderr)
            return 2

    if not state.get("build_finished_at"):
        print("Building benchmark images before timing", flush=True)
        compose = (
            GROUP_PERSISTENT_COMPOSE
            if args.profile == "group-persistent"
            else GO_JUDGE_COMPOSE
        )
        build_services = ["backend", "app_worker", "tests", "judge", "workers"]
        if args.profile == "engine-only":
            build_services.append("go-judge")
        built = subprocess.run(
            compose + ["build", *build_services],
            cwd=ROOT,
            env=environment,
        )
        if built.returncode:
            state["status"] = "build_failed"
            state["build_exit_code"] = built.returncode
            state["updated_at"] = now()
            write_state(state_path, state)
            report(campaign_dir, state)
            return built.returncode
        state["build_finished_at"] = now()
        write_state(state_path, state)

    guard = safety_check(
        state["initial_swap_used_bytes"],
        memory()["available_bytes"] < 2 * 1024**3,
    )
    if guard:
        stop_campaign(campaign_dir, state_path, state, *guard)
        print("Host safety stop after image build", file=sys.stderr)
        return 2

    state["status"] = "running"
    write_state(state_path, state)
    report(campaign_dir, state)
    try:
        for cpu_limit in args.cpu_limits:
            cell_environment = environment.copy()
            cell_environment["RUNNER_EXEC_CPU_LIMIT"] = str(cpu_limit)
            for workers in args.workers:
                matrix_dimensions = len(args.cpu_limits) > 1 or len(args.workers) > 1
                for problem in PROBLEMS:
                    name = cell_label(
                        args.label,
                        problem,
                        workers if matrix_dimensions else None,
                        cpu_limit if matrix_dimensions else None,
                    )
                    cell = state["cells"].setdefault(
                        name,
                        {
                            "problem": problem,
                            "workers": workers,
                            "cpu_limit": cpu_limit,
                            "status": "pending",
                            "attempts": [],
                        },
                    )
                    if cell["status"] == "complete":
                        continue
                    guard = safety_check(
                        state["initial_swap_used_bytes"],
                        memory()["available_bytes"] < 2 * 1024**3,
                    )
                    if guard:
                        stop_campaign(campaign_dir, state_path, state, *guard)
                        return 2

                    attempt = len(cell["attempts"]) + 1
                    result_label = f"{name}-try{attempt:02d}"
                    cell["status"] = "running"
                    cell["attempts"].append(
                        {
                            "label": result_label,
                            "status": "running",
                            "started_at": now(),
                        }
                    )
                    state["updated_at"] = now()
                    write_state(state_path, state)
                    report(campaign_dir, state)
                    command = [
                        sys.executable,
                        "scripts/runner-bench.py",
                        "--label",
                        result_label,
                        "--problem",
                        problem,
                        "--workers",
                        str(workers),
                        "--concurrency",
                        "1",
                        "10",
                        "25",
                        "--repetitions",
                        "3",
                    ]
                    paired_flag = (
                        "--paired-engine-group-persistent"
                        if args.profile == "group-persistent"
                        else "--paired-engine"
                    )
                    command.insert(4, paired_flag)
                    candidate = (
                        "go-judge-group-persistent"
                        if args.profile == "group-persistent"
                        else "go-judge"
                    )
                    print(
                        f"Starting Judge0 versus {candidate}: {problem}, "
                        f"{workers} workers, {cpu_limit} CPU quota",
                        flush=True,
                    )
                    completed = subprocess.run(command, cwd=ROOT, env=cell_environment)
                    attempt_state = cell["attempts"][-1]
                    attempt_state["finished_at"] = now()
                    attempt_state["exit_code"] = completed.returncode
                    result_dir = RESULTS / result_label
                    if completed.returncode:
                        safety_file = (
                            next(result_dir.glob("**/safety-stop.json"), None)
                            if result_dir.exists()
                            else None
                        )
                        if safety_file:
                            attempt_state["status"] = "safety_stopped"
                            state["status"] = "safety_stopped"
                            state["safety_stopped"] = True
                            cell["status"] = "safety_stopped"
                            attempt_state["safety_stop"] = str(
                                safety_file.relative_to(ROOT)
                            )
                        else:
                            attempt_state["status"] = "incomplete"
                            cell["status"] = "incomplete"
                            state["status"] = "incomplete"
                        state["updated_at"] = now()
                        write_state(state_path, state)
                        report(campaign_dir, state)
                        return completed.returncode

                    compared = subprocess.run(
                        [
                            sys.executable,
                            "scripts/compare-runner-bench.py",
                            str(result_dir.relative_to(ROOT)),
                            "--candidate",
                            candidate,
                        ],
                        cwd=ROOT,
                        env=cell_environment,
                    )
                    if compared.returncode:
                        attempt_state["status"] = "comparison_failed"
                        cell["status"] = "incomplete"
                        state["status"] = "incomplete"
                        state["updated_at"] = now()
                        write_state(state_path, state)
                        report(campaign_dir, state)
                        return compared.returncode
                    comparison = json.loads(
                        (result_dir / "comparison.json").read_text()
                    )
                    if len(comparison.get("pairs", [])) != 9 or comparison.get(
                        "incomplete_runs"
                    ):
                        attempt_state["status"] = "incomplete_pairs"
                        cell["status"] = "incomplete"
                        state["status"] = "incomplete"
                        state["updated_at"] = now()
                        write_state(state_path, state)
                        report(campaign_dir, state)
                        return 1
                    attempt_state["status"] = "complete"
                    cell.update(
                        status="complete",
                        result_label=result_label,
                        finished_at=now(),
                        pair_count=len(comparison["pairs"]),
                    )
                    state["updated_at"] = now()
                    write_state(state_path, state)
                    report(campaign_dir, state)

        state["status"] = "complete"
        state["finished_at"] = now()
        state["updated_at"] = now()
        write_state(state_path, state)
        report(campaign_dir, state)
        print(f"Campaign complete: {state_path}", flush=True)
        return 0
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        state["updated_at"] = now()
        write_state(state_path, state)
        report(campaign_dir, state)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
