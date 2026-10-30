from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
from app.core.config import settings
from app.core.errors import ApiError
from app.models import (
    ComplexityAnalysis,
    ComplexityAnalysisStatus,
    Problem,
    Submission,
    SubmissionStatus,
    User,
)
from app.routers.submissions import get_submission_complexity
from app.services.complexity_analysis import (
    COMPLEXITY_LABELS,
    ComplexityError,
    classify_code,
    process_analysis,
    process_next_analysis,
    queue_submission_analysis,
)
from sqlalchemy import select


def _ollama_client(body):
    def respond(request):
        return httpx.Response(
            200,
            json={"message": {"content": body}},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_classify_code_requests_json_and_validates_labels(monkeypatch):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "http://ollama:11434")
    client = _ollama_client('{"time":"O(n*m)","space":"O(V+E)"}')
    time_label, space_label = classify_code(
        "def f(x): return x", "example", "input sizes n and m", client=client
    )
    assert (time_label, space_label) == ("O(n*m)", "O(V+E)")
    assert time_label in COMPLEXITY_LABELS
    client.close()


def test_classify_code_rejects_invalid_or_non_json_labels(monkeypatch):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "http://ollama:11434")
    client = _ollama_client('{"time":"O(magic)","space":"O(1)"}')
    with pytest.raises(ComplexityError, match="invalid_response"):
        classify_code("pass", "example", "", client=client)
    client.close()


def test_classify_code_fails_closed_when_ollama_is_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "")
    with pytest.raises(ComplexityError, match="not_configured"):
        classify_code("pass", "example", "")


def test_submission_complexity_is_queued_and_owner_scoped(db_session, monkeypatch):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "http://ollama:11434")
    problem = db_session.scalar(select(Problem).limit(1))
    submission = Submission(
        student_id=2,
        problem_id=problem.id,
        source_code="def sum_list(xs): return sum(xs)",
        status=SubmissionStatus.QUEUED,
    )
    db_session.add(submission)
    db_session.flush()
    queue_submission_analysis(db_session, submission)
    db_session.commit()
    response = get_submission_complexity(
        submission.id, db_session, db_session.get(User, 2)
    )
    assert response["status"] == "queued"
    assert response["time_complexity"] is None
    with pytest.raises(ApiError) as error:
        get_submission_complexity(submission.id, db_session, db_session.get(User, 1))
    assert error.value.status_code == 404
    row = db_session.get(ComplexityAnalysis, submission.id)
    assert row is not None
    assert row.model == settings.BIG_O_OLLAMA_MODEL


def test_analysis_failure_retries_without_touching_submission_result(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "http://ollama:11434")
    problem = db_session.scalar(select(Problem).limit(1))
    submission = Submission(
        student_id=1,
        problem_id=problem.id,
        source_code="def solution(values): return len(values)",
        status=SubmissionStatus.PASSED,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(submission)
    db_session.flush()
    analysis = ComplexityAnalysis(
        submission_id=submission.id,
        status=ComplexityAnalysisStatus.PROCESSING,
        model=settings.BIG_O_OLLAMA_MODEL,
        prompt_version="1",
        attempt_count=1,
    )
    db_session.add(analysis)
    db_session.commit()
    with patch(
        "app.services.complexity_analysis.classify_code",
        side_effect=ComplexityError("timeout"),
    ):
        assert process_analysis(db_session, submission.id) is True
    db_session.refresh(analysis)
    db_session.refresh(submission)
    assert analysis.status == ComplexityAnalysisStatus.QUEUED
    assert analysis.error_code == "timeout"
    assert analysis.next_attempt_at is not None
    assert submission.status == SubmissionStatus.PASSED


def test_analysis_worker_persists_classification_without_calling_grader(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "BIG_O_OLLAMA_URL", "http://ollama:11434")
    problem = db_session.scalar(select(Problem).limit(1))
    submission = Submission(
        student_id=2,
        problem_id=problem.id,
        source_code="def solution(values): return len(values)",
        status=SubmissionStatus.PASSED,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
        is_practice_run=False,
    )
    db_session.add(submission)
    db_session.flush()
    db_session.add(
        ComplexityAnalysis(
            submission_id=submission.id,
            status=ComplexityAnalysisStatus.QUEUED,
            model=settings.BIG_O_OLLAMA_MODEL,
            prompt_version="1",
        )
    )
    db_session.commit()
    with patch(
        "app.services.complexity_analysis.classify_code",
        return_value=("O(n)", "O(1)"),
    ) as classify:
        assert process_next_analysis(db_session) is True
    result = db_session.get(ComplexityAnalysis, submission.id)
    assert result.status == ComplexityAnalysisStatus.COMPLETE
    assert result.time_complexity == "O(n)"
    assert result.space_complexity == "O(1)"
    assert result.analyzed_at is not None
    classify.assert_called_once()
