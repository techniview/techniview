from pathlib import Path

from performance.comparison import (
    append_measured_result,
    workload_overlay,
)
from performance.regression import compare_reports


def reports(*durations: float) -> list[dict[str, float]]:
    return [{"completion_batch_seconds": duration} for duration in durations]


def test_regression_gate_requires_both_relative_and_absolute_thresholds() -> None:
    relative_only = compare_reports(reports(10, 10, 10), reports(12.1, 12.1, 12.1))
    absolute_only = compare_reports(reports(10, 10, 10), reports(12, 12, 12))
    both = compare_reports(reports(10, 10, 100), reports(17, 17, 100))

    assert relative_only["regression_gate_failed"] is False
    assert absolute_only["regression_gate_failed"] is False
    assert both["regression_gate_failed"] is True
    assert both["base_median_completion_batch_seconds"] == 10
    assert both["proposed_median_completion_batch_seconds"] == 17


def test_regression_gate_uses_medians_not_the_slowest_run() -> None:
    result = compare_reports(reports(9, 10, 500), reports(16, 17, 900))

    assert result["base_median_completion_batch_seconds"] == 10
    assert result["proposed_median_completion_batch_seconds"] == 17
    assert result["regression_gate_failed"] is True


def test_compose_overlay_builds_each_application_revision_separately() -> None:
    overlay = workload_overlay(
        application_backend=Path("/base/backend"),
        test_backend=Path("/proposed/backend"),
        source_commit="base-sha",
    )

    assert overlay.count('context: "/base/backend"') == 2
    assert overlay.count('SOURCE_COMMIT: "base-sha"') == 2
    assert 'context: "/proposed/backend"' in overlay


def test_measured_report_is_written_before_the_next_measurement(tmp_path) -> None:
    output_path = tmp_path / "base-short.json"
    record: dict[str, object] = {"measured": []}
    measured = {"completion_batch_seconds": 1.25}

    append_measured_result(record, measured, output_path)

    assert output_path.exists()
    assert '"completion_batch_seconds": 1.25' in output_path.read_text()
