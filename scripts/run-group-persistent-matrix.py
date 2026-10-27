#!/usr/bin/env python3
"""Run or resume the six-cell grouped-worker comparison as one guarded campaign."""

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
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    "/dev/null",
    "-p",
    "techniview-runner-bench",
    "-f",
    "compose.integration.yml",
    "-f",
    "compose.benchmark.yml",
]
MATRIX = (
    ("Ransom Note", 8),
    ("Ransom Note", 16),
    ("Number of Islands", 8),
    ("Number of Islands", 16),
    ("Minimum Cost for Tickets", 8),
    ("Minimum Cost for Tickets", 16),
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


def write_report(path, state):
    lines = [
        f"# Runner benchmark campaign: {state['label']}",
        "",
        f"Status: **{state['status']}**",
        "",
        f"Source commit: `{state['source_commit']}`",
        "",
        "| Workload | Runner workers | Status | Comparison |",
        "| --- | ---: | --- | --- |",
    ]
    for problem, workers in MATRIX:
        label = experiment_label(state["label"], problem, workers)
        cell = state.get("cells", {}).get(label, {})
        comparison = (
            f"[{label}](../{label}/comparison.md)"
            if cell.get("status") == "complete"
            else "—"
        )
        lines.append(
            f"| {problem} | {workers} | {cell.get('status', 'pending')} "
            f"| {comparison} |"
        )
    stop_path = path.parent / "safety-stop.json"
    if stop_path.exists():
        lines.extend(
            [
                "",
                "The campaign stopped under its host safety limits. See "
                "[safety-stop.json](safety-stop.json).",
            ]
        )
    path.with_name("REPORT.md").write_text("\n".join(lines) + "\n")


def preflight_safety_stop(initial_swap, initial_low_memory):
    low_since = time.monotonic() if initial_low_memory else None
    while low_since is not None:
        current = memory()
        reason, low_since = stop_reason(
            initial_swap, current, time.monotonic(), low_since
        )
        if reason:
            return reason, current
        if low_since is None:
            return None
        time.sleep(0.25)
    current = memory()
    reason, _ = stop_reason(initial_swap, current, time.monotonic(), None)
    return (reason, current) if reason else None


def record_safety_stop(campaign_dir, state_path, state, reason, sample):
    (campaign_dir / "safety-stop.json").write_text(
        json.dumps(
            {
                "reason": reason,
                "at": now(),
                "campaign_initial_swap_used_bytes": state[
                    "campaign_initial_swap_used_bytes"
                ],
                "campaign_swap_growth_bytes": (
                    sample["swap_used_bytes"]
                    - state["campaign_initial_swap_used_bytes"]
                ),
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
    write_report(campaign_dir / "REPORT.md", state)


def experiment_label(prefix, problem, workers):
    problem_slug = problem.lower().replace(" ", "-")
    return f"{prefix}-{problem_slug}-w{workers}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Unique campaign label prefix")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    root = ROOT / "benchmark-results/local-runner"
    campaign_dir = root / f"{args.label}-campaign"
    state_path = campaign_dir / "campaign.json"
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    current_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    current_memory = memory()

    if args.resume:
        if not state_path.exists():
            parser.error("--resume requires an existing campaign manifest")
        state = json.loads(state_path.read_text())
        if state["source_commit"] != source_commit:
            parser.error("campaign source commit differs; start with a new label")
        if state["boot_id"] != current_boot:
            state.setdefault("sessions", []).append(
                {
                    "boot_id": current_boot,
                    "started_at": now(),
                    "swap_used_at_start_bytes": current_memory["swap_used_bytes"],
                    "available_at_start_bytes": current_memory["available_bytes"],
                    "reason": "new host boot; reset the host safety baseline",
                }
            )
            state["boot_id"] = current_boot
            state["campaign_initial_swap_used_bytes"] = current_memory[
                "swap_used_bytes"
            ]
            state["campaign_initial_memory"] = current_memory
            state["safety_stopped"] = False
        elif state.get("safety_stopped"):
            parser.error(
                "campaign hit a host safety stop on this boot; wait for a reboot "
                "before resuming, or start a new campaign after the host recovers"
            )
    else:
        if state_path.exists():
            parser.error("campaign already exists; use --resume or choose a new label")
        campaign_dir.mkdir(parents=True)
        state = {
            "version": 1,
            "label": args.label,
            "status": "running",
            "source_commit": source_commit,
            "boot_id": current_boot,
            "started_at": now(),
            "campaign_initial_swap_used_bytes": current_memory["swap_used_bytes"],
            "campaign_initial_memory": current_memory,
            "machine": platform.uname()._asdict(),
            "cpu": Path("/proc/cpuinfo").read_text(),
            "cells": {},
            "sessions": [],
        }

    if state.get("safety_stopped"):
        parser.error("campaign is safety-stopped; do not restart load on this boot")

    guard = preflight_safety_stop(
        state["campaign_initial_swap_used_bytes"],
        current_memory["available_bytes"] < 2 * 1024**3,
    )
    if guard:
        reason, sample = guard
        record_safety_stop(campaign_dir, state_path, state, reason, sample)
        print(f"Host safety stop before load: {reason}", file=sys.stderr)
        return 2

    state["status"] = "running"
    state["updated_at"] = now()
    write_state(state_path, state)
    write_report(campaign_dir / "REPORT.md", state)
    environment = os.environ.copy()
    environment["RUNNER_BENCH_CAMPAIGN_SWAP_BASELINE_BYTES"] = str(
        state["campaign_initial_swap_used_bytes"]
    )

    build_command = COMPOSE + [
        "-f",
        "compose.go-judge-shared.yml",
        "-f",
        "compose.group-experiment.yml",
        "-f",
        "compose.persistent-workers.yml",
        "build",
        "backend",
        "app_worker",
        "tests",
        "judge",
        "workers",
    ]
    print("Building benchmark images before timing", flush=True)
    build_result = subprocess.run(build_command, cwd=ROOT, env=environment)
    if build_result.returncode:
        state["status"] = "build_failed"
        state["build_exit_code"] = build_result.returncode
        state["updated_at"] = now()
        write_state(state_path, state)
        write_report(campaign_dir / "REPORT.md", state)
        return build_result.returncode
    state["build_finished_at"] = now()
    write_state(state_path, state)
    guard = preflight_safety_stop(
        state["campaign_initial_swap_used_bytes"],
        memory()["available_bytes"] < 2 * 1024**3,
    )
    if guard:
        reason, sample = guard
        record_safety_stop(campaign_dir, state_path, state, reason, sample)
        print(f"Host safety stop after image build: {reason}", file=sys.stderr)
        return 2

    try:
        for problem, workers in MATRIX:
            label = experiment_label(args.label, problem, workers)
            cell = state["cells"].setdefault(
                label, {"problem": problem, "workers": workers, "status": "pending"}
            )
            if cell["status"] == "complete":
                continue
            guard = preflight_safety_stop(
                state["campaign_initial_swap_used_bytes"],
                memory()["available_bytes"] < 2 * 1024**3,
            )
            if guard:
                reason, sample = guard
                record_safety_stop(campaign_dir, state_path, state, reason, sample)
                print(f"Host safety stop before {label}: {reason}", file=sys.stderr)
                return 2
            output_dir = root / label
            command = [
                sys.executable,
                "scripts/runner-bench.py",
                "--label",
                label,
                "--paired-group-persistent",
                "--engine",
                "go-judge-shared",
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
            if (output_dir / "metadata.json").exists():
                command.append("--resume")
            print(f"Starting {label}", flush=True)
            cell["status"] = "running"
            cell["started_at"] = now()
            write_state(state_path, state)
            write_report(campaign_dir / "REPORT.md", state)
            completed = subprocess.run(command, cwd=ROOT, env=environment)
            cell["finished_at"] = now()
            cell["exit_code"] = completed.returncode
            if completed.returncode:
                safety_file = (
                    next(output_dir.glob("**/safety-stop.json"), None)
                    if output_dir.exists()
                    else None
                )
                if safety_file:
                    cell["status"] = "safety_stopped"
                    cell["safety_stop"] = str(safety_file.relative_to(ROOT))
                    state["safety_stopped"] = True
                    state["status"] = "safety_stopped"
                else:
                    cell["status"] = "incomplete"
                    state["status"] = "incomplete"
                state["updated_at"] = now()
                write_state(state_path, state)
                write_report(campaign_dir / "REPORT.md", state)
                return completed.returncode
            subprocess.run(
                [
                    sys.executable,
                    "scripts/compare-runner-bench.py",
                    str(output_dir.relative_to(ROOT)),
                    "--candidate",
                    "group-persistent",
                ],
                cwd=ROOT,
                check=True,
            )
            cell["status"] = "complete"
            state["updated_at"] = now()
            write_state(state_path, state)
            write_report(campaign_dir / "REPORT.md", state)
        state["status"] = "complete"
        state["finished_at"] = now()
        write_state(state_path, state)
        write_report(campaign_dir / "REPORT.md", state)
        print(f"Campaign complete: {state_path}", flush=True)
        return 0
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        state["updated_at"] = now()
        write_state(state_path, state)
        write_report(campaign_dir / "REPORT.md", state)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
