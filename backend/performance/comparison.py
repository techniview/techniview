"""Shared helpers for building and persisting benchmark comparison reports."""

import json
from pathlib import Path


def workload_overlay(
    application_backend: Path, test_backend: Path, source_commit: str
) -> str:
    dockerfile = json.dumps(str(test_backend / "integration/Dockerfile"))
    application_build = (
        f"build:\n      context: {json.dumps(str(application_backend))}\n"
        f"      dockerfile: {dockerfile}\n"
        "      args:\n"
        f"        SOURCE_COMMIT: {json.dumps(source_commit)}\n"
    )
    return (
        "services:\n"
        "  backend:\n"
        f"    {application_build}"
        "  app_worker:\n"
        f"    {application_build}"
        "  tests:\n"
        f"    build:\n      context: {json.dumps(str(test_backend))}\n"
    )


def write_json(path: Path, value: dict[str, object]) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


def append_measured_result(
    workload_record: dict[str, object], report: dict[str, object], output_path: Path
) -> None:
    workload_record["measured"].append(report)
    write_json(output_path, workload_record)
