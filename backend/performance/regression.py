"""Pure comparison logic for the performance regression gate."""

from statistics import median

REGRESSION_RATIO = 1.5
REGRESSION_SECONDS = 2.0


def compare_reports(base: list[dict], proposed: list[dict]) -> dict[str, float | bool]:
    """Apply the two-part gate to three-run completion batch measurements."""
    base_median = median(report["completion_batch_seconds"] for report in base)
    proposed_median = median(report["completion_batch_seconds"] for report in proposed)
    delta = proposed_median - base_median
    ratio = proposed_median / base_median if base_median else float("inf")
    return {
        "base_median_completion_batch_seconds": base_median,
        "proposed_median_completion_batch_seconds": proposed_median,
        "delta_seconds": delta,
        "ratio": ratio,
        "regression_gate_failed": (
            delta > REGRESSION_SECONDS and ratio > REGRESSION_RATIO
        ),
    }
