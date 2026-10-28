#!/usr/bin/env python3
"""Summarize paired bursts without treating small-sample tails as guarantees."""

import argparse
import json
import statistics
from math import ceil
from pathlib import Path


def percentile(values, fraction):
    return sorted(values)[max(0, ceil(len(values) * fraction) - 1)]


def read_stage_samples(path):
    stages = {}
    if not path.exists():
        return stages
    for line in path.read_text().splitlines():
        start = line.find('{"event":')
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
        except ValueError:
            continue
        if event.get("event") == "runner_stage":
            stages.setdefault(event["stage"], []).append(event["seconds"])
        elif event.get("event") == "runner_request_completed":
            stages.setdefault("app_" + event["operation"], []).append(event["seconds"])
    return stages


def summarize_stages(stages):
    return {
        stage: {
            "count": len(values),
            "p50": statistics.median(values),
            "p95": percentile(values, 0.95),
            "total_seconds": sum(values),
        }
        for stage, values in stages.items()
    }


def parse_cgroup_values(raw):
    values = {}
    for line in raw.splitlines():
        name, value = line.split(maxsplit=1)
        values[name] = int(value)
    return values


def summarize_worker_resources(directory):
    """Summarize execution-service usage for one measured burst."""
    containers_path = directory / "containers.json"
    samples_path = directory / "resources.jsonl"
    if not containers_path.exists() or not samples_path.exists():
        return None

    services = {
        item["Id"]: item.get("Config", {})
        .get("Labels", {})
        .get("com.docker.compose.service")
        for item in json.loads(containers_path.read_text())
    }
    worker_ids = {
        container_id for container_id, name in services.items() if name == "workers"
    }
    if not worker_ids:
        return None

    first = None
    last = None
    memory_peak = 0
    first_oom_count = None
    last_oom_count = 0
    for line in samples_path.read_text().splitlines():
        sample = json.loads(line)
        for container_id in worker_ids:
            cgroup = sample.get("cgroups", {}).get(container_id)
            if not cgroup or "cpu.stat" not in cgroup:
                continue
            counters = parse_cgroup_values(cgroup["cpu.stat"])
            current = {
                "elapsed_seconds": sample["elapsed_seconds"],
                "usage_usec": counters.get("usage_usec", 0),
                "nr_periods": counters.get("nr_periods", 0),
                "nr_throttled": counters.get("nr_throttled", 0),
                "throttled_usec": counters.get("throttled_usec", 0),
                "oom_count": 0,
            }
            events = parse_cgroup_values(cgroup.get("memory.events", ""))
            current["oom_count"] = events.get("oom", 0) + events.get("oom_kill", 0)
            if first is None:
                first = current
                first_oom_count = current["oom_count"]
            last = current
            memory_peak = max(
                memory_peak,
                int(cgroup.get("memory.current", "0").strip() or 0),
            )
            last_oom_count = current["oom_count"]

    if first is None or last is None:
        return None
    elapsed = max(last["elapsed_seconds"] - first["elapsed_seconds"], 0)
    usage = max(last["usage_usec"] - first["usage_usec"], 0) / 1_000_000
    periods = max(last["nr_periods"] - first["nr_periods"], 0)
    throttled = max(last["nr_throttled"] - first["nr_throttled"], 0)
    return {
        "worker_cpu_seconds": usage,
        "average_worker_cpu_cores": usage / elapsed if elapsed else 0,
        "throttled_period_fraction": throttled / periods if periods else 0,
        "worker_memory_peak_bytes": memory_peak,
        "worker_oom_events": max(last_oom_count - (first_oom_count or 0), 0),
        "sampled_elapsed_seconds": elapsed,
    }


def summarize_resource_variants(directory, pairs, baseline, candidate):
    metrics = {baseline: {}, candidate: {}}
    for pair in pairs:
        for variant in (baseline, candidate):
            path = directory / f"{pair['pair']}-{variant}"
            sample = summarize_worker_resources(path)
            if sample is None:
                continue
            for name, value in sample.items():
                metrics[variant].setdefault(name, []).append(value)
    return {
        variant: {
            "burst_count": max((len(values) for values in grouped.values()), default=0),
            **{
                name: {
                    "median": statistics.median(values),
                    "maximum": max(values),
                }
                for name, values in grouped.items()
            },
        }
        for variant, grouped in metrics.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--candidate",
        choices=[
            "pooled",
            "outbox",
            "dispatch",
            "go-judge",
            "go-judge-shared",
            "go-judge-group-persistent",
            "combined",
            "grouped",
            "persistent",
            "shared-python",
            "group-persistent",
        ],
        default="pooled",
    )
    parser.add_argument(
        "--baseline",
        choices=["baseline", "go-judge-shared", "grouped"],
        default="baseline",
    )
    args = parser.parse_args()
    output_stem = (
        "comparison"
        if args.baseline == "baseline"
        else f"comparison-{args.baseline}-to-{args.candidate}"
    )
    incomplete = [
        str(path.parent.name)
        for path in sorted(args.directory.glob("*/summary.json"))
        if not json.loads(path.read_text())["complete"]
    ]
    pairs = []
    for baseline in sorted(args.directory.glob(f"c*-r*-{args.baseline}/summary.json")):
        candidate = (
            baseline.parent.with_name(
                baseline.parent.name.removesuffix(f"-{args.baseline}")
                + f"-{args.candidate}"
            )
            / "summary.json"
        )
        if not candidate.exists():
            continue
        before = json.loads(baseline.read_text())
        after = json.loads(candidate.read_text())
        if not (before["complete"] and after["complete"]):
            continue
        row = {
            "pair": baseline.parent.name.removesuffix(f"-{args.baseline}"),
            "concurrency": before["concurrency"],
            "metrics": {},
        }
        for metric in (
            "acceptance_latency_seconds",
            "api_submission_to_result_seconds",
            "submission_to_completion_seconds",
        ):
            row["metrics"][metric] = {}
            for stat in ("p50", "p95", "p99", "max"):
                a = before["measurements"][metric][stat]
                b = after["measurements"][metric][stat]
                row["metrics"][metric][stat] = {
                    "baseline": a,
                    "candidate": b,
                    "difference_seconds": b - a,
                    "change_percent": (b - a) / a * 100 if a else None,
                }
        a = (
            before["concurrency"]
            / before["measurements"]["api_completion_batch_seconds"]
        )
        b = after["concurrency"] / after["measurements"]["api_completion_batch_seconds"]
        row["completed_submissions_per_second"] = {
            "baseline": a,
            "candidate": b,
            "difference": b - a,
            "change_percent": (b - a) / a * 100,
        }
        pairs.append(row)
    stages = read_stage_samples(args.directory / "services.log")
    stage_summary = summarize_stages(stages)
    variants = {args.baseline: {}, args.candidate: {}}
    for pair in pairs:
        for variant, collected in variants.items():
            path = args.directory / f"{pair['pair']}-{variant}" / "services.log"
            for stage, values in read_stage_samples(path).items():
                collected.setdefault(stage, []).extend(values)
    metadata_path = args.directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    resource_summary = summarize_resource_variants(
        args.directory, pairs, args.baseline, args.candidate
    )
    report = {
        "experiment_configuration": metadata,
        "runner_cpu_limit": metadata.get("runner_cpu_limit", 6),
        "baseline_variant": args.baseline,
        "candidate_variant": args.candidate,
        "pairs": pairs,
        "incomplete_runs": incomplete,
        "stages_by_variant_excluding_warmups": {
            name: summarize_stages(values) for name, values in variants.items()
        },
        "runner_worker_resources_by_variant_excluding_warmups": resource_summary,
        "runner_stages_all_bursts_including_warmups": stage_summary,
        "caveat": "Small-sample p99 values are diagnostic, not production guarantees.",
    }
    (args.directory / f"{output_stem}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    lines = [
        f"# Local {args.candidate} comparison",
        "",
        "Times run from request start to completed results received through the API.",
        "Negative changes mean lower latency. Paired results exclude warm-ups.",
        "",
        "| Pair | API p50 before (s) | API p50 after (s) | Difference (s) | Change |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for pair in pairs:
        value = pair["metrics"]["api_submission_to_result_seconds"]["p50"]
        lines.append(
            f"| {pair['pair']} | {value['baseline']:.3f} | {value['candidate']:.3f} | "
            f"{value['difference_seconds']:+.3f} | {value['change_percent']:+.1f}% |"
        )
    lines += [
        "",
        report["caveat"],
        "",
        "See the companion JSON for acceptance, server completion, and API tails.",
        "Stage aggregates include both variants and warm-ups. "
        "They cannot attribute changes to one variant.",
    ]
    if all(
        resource_summary.get(variant, {}).get("burst_count") for variant in variants
    ):
        lines += [
            "",
            "Runner container resource sample medians across measured bursts:",
            "",
            "| Variant | CPU cores used | Throttled periods | "
            "Peak sampled memory | OOM events |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for variant in (args.baseline, args.candidate):
            summary = resource_summary[variant]
            memory_gib = summary["worker_memory_peak_bytes"]["median"] / (1024**3)
            oom_events = summary["worker_oom_events"]["maximum"]
            lines.append(
                f"| {variant} | "
                f"{summary['average_worker_cpu_cores']['median']:.2f} | "
                f"{summary['throttled_period_fraction']['median'] * 100:.1f}% | "
                f"{memory_gib:.2f} GiB | {oom_events} |"
            )
    lines += [
        "",
        "The public submission API and grading behavior are unchanged.",
    ]
    if incomplete:
        lines += [
            "",
            "Incomplete runs excluded: " + ", ".join(incomplete) + ".",
            "Further load stopped under the specified resource safety policy.",
        ]
    if not stages:
        lines += [
            "",
            "No runner stage samples were captured in this comparison.",
            "The initial timing logger used a suppressed log level. "
            "Logging is fixed for subsequent verification and experiments.",
        ]
    (args.directory / f"{output_stem}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
