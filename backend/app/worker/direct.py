"""Durable direct attempts, fenced by the submission claim and case attempt ID."""

from uuid import uuid4

from ..core import go_judge
from ..routers import submissions as results
from ..services.progress import utc_now


def process_submission(db, submission_id: int, owner: str) -> None:
    from .submissions import _mark_infrastructure_failure

    row = results._load_submission(db, submission_id)
    if row is None or row.claim_owner != owner:
        db.rollback()
        return
    case_ids = [
        case.test_case_id
        for case in sorted(row.case_results, key=lambda c: c.case_order)
    ]
    db.commit()
    for case_id in case_ids:
        row = results._load_submission(db, submission_id)
        if (
            row is None
            or row.claim_owner != owner
            or row.status in results.TERMINAL_SUBMISSION_STATUSES
        ):
            db.rollback()
            return
        case = next(c for c in row.case_results if c.test_case_id == case_id)
        if results._is_terminal(case.judge0_status_id):
            db.commit()
            continue
        if case.dispatch_started_at is not None:
            # A previous owner recorded dispatch but never durably saved a result.
            _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
            results._finalize_submission(db, row)
            db.commit()
            continue
        attempt = str(uuid4())
        case.judge0_token = attempt
        case.dispatch_started_at = utc_now()
        case.dispatch_attempt_count += 1
        case.judge0_status_id = 2
        row.claimed_at = utc_now()
        execution = go_judge.Execution(
            case.execution_source,
            case.execution_stdin,
            case.execution_expected_output,
            float(case.cpu_time_limit_seconds),
            case.memory_limit_kb,
        )
        db.commit()
        try:
            report = go_judge.execute(execution)
        except go_judge.OutcomeUnknown:
            report = None
        row = results._load_submission(db, submission_id)
        if row is None or row.claim_owner != owner:
            db.rollback()
            return
        case = next(c for c in row.case_results if c.test_case_id == case_id)
        if case.judge0_token != attempt or results._is_terminal(case.judge0_status_id):
            db.rollback()
            return
        if report is None:
            _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
        else:
            results._update_case_result(case, report)
            if case.infrastructure_error:
                row.failure_code = "runner_internal_error"
        results._finalize_submission(db, row)
        db.commit()
    row = results._load_submission(db, submission_id)
    if row is not None and row.claim_owner == owner:
        results._finalize_submission(db, row)
        row.claim_owner = None
        row.claimed_at = None
        row.next_check_at = None
        db.commit()
    else:
        db.rollback()
