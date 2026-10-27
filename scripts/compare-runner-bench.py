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
    report = {
        "experiment_configuration": metadata,
        "baseline_variant": args.baseline,
        "candidate_variant": args.candidate,
        "pairs": pairs,
        "incomplete_runs": incomplete,
        "stages_by_variant_excluding_warmups": {
            name: summarize_stages(values) for name, values in variants.items()
        },
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
