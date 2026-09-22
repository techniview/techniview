from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from app.models import AssignmentItem, StudentPracticeProgress, SubmissionCaseResult
from sqlalchemy import select

pytestmark = pytest.mark.anyio


async def test_status_messages_cover_all_known_ids():
    from app.routers.submissions import get_status_message

    for status_id in range(1, 15):
        msg = get_status_message(status_id)
        assert isinstance(msg, str) and msg
        assert "Unknown" not in msg
    assert "Unknown" in get_status_message(999)


async def _first_problem_id(client) -> int:
    return (await client.get("/api/problems")).json()["items"][0]["id"]


async def _problem_id(client, title: str) -> int:
    problems = (await client.get("/api/problems")).json()["items"]
    return next(item["id"] for item in problems if item["title"] == title)


async def test_create_validates_empty_source(student_client):
    problem_id = await _first_problem_id(student_client)
    response = await student_client.post(
        "/api/submissions",
        json={"source_code": "", "problem_id": problem_id},
    )
    assert response.status_code == 422


async def test_create_rejects_client_owned_grading_fields(student_client):
    problem_id = await _first_problem_id(student_client)
    response = await student_client.post(
        "/api/submissions",
        json={
            "source_code": "print(1)",
            "problem_id": problem_id,
            "stdin": "anything",
            "expected_output": "anything",
            "cpu_time_limit": 1000,
        },
    )
    assert response.status_code == 422


async def test_create_rejects_non_python_language(student_client):
    problem_id = await _first_problem_id(student_client)
    with patch("app.routers.submissions.judge0_submit") as mock_submit:
        response = await student_client.post(
            "/api/submissions",
            json={
                "source_code": "print(1)",
                "problem_id": problem_id,
                "language_id": 54,
            },
        )
        assert response.status_code == 422
        mock_submit.assert_not_called()


async def test_get_rejects_bad_id_without_calling_judge0(student_client):
    with patch("app.routers.submissions.judge0_get") as mock_get:
        response = await student_client.get("/api/submissions/not-an-id")
        assert response.status_code == 422
        mock_get.assert_not_called()


async def test_submission_runs_every_server_owned_test_without_exposing_hidden_case(
    student_client,
):
    problem_id = await _problem_id(student_client, "Sum a List")
    judge0_responses = [
        {"token": "public-token", "status": {"id": 3}},
        {"token": "hidden-token", "status": {"id": 4}},
    ]
    with patch(
        "app.routers.submissions.judge0_submit",
        side_effect=judge0_responses,
    ) as mock_submit:
        response = await student_client.post(
            "/api/submissions?wait=true",
            json={
                "source_code": "def sum_list(values):\n    return sum(values)\n",
                "problem_id": problem_id,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["done"] is True
    assert body["status"] == "failed"
    assert body["passed_count"] == 1
    assert body["test_count"] == 2
    assert len(body["public_results"]) == 1
    assert "[[-2, 2]]" not in response.text
    assert "hidden-token" not in response.text
    assert mock_submit.call_count == 2
    assert [call.args[3] for call in mock_submit.call_args_list] == ["6", "0"]
    for call in mock_submit.call_args_list:
        assert "__techniview_target" in call.args[0]


async def test_wait_result_persists_judge0_report_fields(student_client, db_session):
    problem_id = await _problem_id(student_client, "Count Evens")
    response_data = {
        "token": "report-token",
        "status": {"id": 3},
        "time": "0.125",
        "memory": 42.2,
        "stdout": "2\n",
        "stderr": "",
        "compile_output": None,
    }
    with patch("app.routers.submissions.judge0_submit", return_value=response_data):
        response = await student_client.post(
            "/api/submissions?wait=true",
            json={"source_code": "print(2)", "problem_id": problem_id},
        )

    assert response.status_code == 200
    result = db_session.scalar(
        select(SubmissionCaseResult).where(
            SubmissionCaseResult.judge0_token == "report-token"
        )
    )
    assert result is not None
    assert result.execution_time_ms == 125
    assert result.memory_kb == 43
    assert result.stdout == "2\n"
    assert result.stderr == ""
    assert result.compile_output is None


async def test_callback_completes_submission_without_polling(
    student_client, db_session
):
    problem_id = await _problem_id(student_client, "Sum a List")
    responses = [
        {"token": "callback-token-1"},
        {"token": "callback-token-2"},
    ]
    with patch(
        "app.routers.submissions.judge0_submit", side_effect=responses
    ) as mock_submit:
        response = await student_client.post(
            "/api/submissions",
            json={"source_code": "print(2)", "problem_id": problem_id},
        )

    assert response.status_code == 200
    assert response.json()["done"] is False
    callback_paths = [
        urlsplit(call.kwargs["callback_url"]).path
        for call in mock_submit.call_args_list
    ]
    for path, token in zip(
        callback_paths, ("callback-token-1", "callback-token-2"), strict=True
    ):
        callback = await student_client.put(
            path,
            json={
                "token": token,
                "status": {"id": 3},
                "time": 0.01,
                "memory": 12,
                "stdout": "Mgo=",
            },
        )
        assert callback.status_code == 200

    final = await student_client.get(f"/api/submissions/{response.json()['id']}")
    assert final.status_code == 200
    assert final.json()["status"] == "passed"
    assert final.json()["done"] is True
    rows = db_session.scalars(
        select(SubmissionCaseResult).where(
            SubmissionCaseResult.judge0_token.in_(
                ("callback-token-1", "callback-token-2")
            )
        )
    ).all()
    assert len(rows) == 2
    assert all(row.execution_time_ms == 10 for row in rows)


async def test_poll_flow_updates_progress_once_per_submission(
    student_client,
    db_session,
):
    token = "f83d50c3-bda9-437c-a396-8466b1f944b0"
    retry_token = "2ba92815-810a-42f1-8f76-a752a7c1bf05"
    problem_id = await _problem_id(student_client, "Count Evens")
    with patch("app.routers.submissions.judge0_submit", return_value={"token": token}):
        response = await student_client.post(
            "/api/submissions",
            json={"source_code": "print(42)", "problem_id": problem_id},
        )
    assert response.status_code == 200
    body = response.json()
    submission_id = body["id"]
    assert body["done"] is False
    assert body["poll_url"] == f"/api/submissions/{submission_id}"

    with patch(
        "app.routers.submissions.judge0_get",
        return_value={"token": token, "status": {"id": 3}},
    ):
        response = await student_client.get(f"/api/submissions/{submission_id}")
        assert response.status_code == 200
        assert response.json()["done"] is True
        second_poll = await student_client.get(f"/api/submissions/{submission_id}")
        assert second_poll.status_code == 200

    with patch(
        "app.routers.submissions.judge0_submit",
        return_value={"token": retry_token},
    ):
        retry = await student_client.post(
            "/api/submissions",
            json={"source_code": "print(0)", "problem_id": problem_id},
        )
    retry_id = retry.json()["id"]
    with patch(
        "app.routers.submissions.judge0_get",
        return_value={"token": retry_token, "status": {"id": 4}},
    ):
        failed_retry = await student_client.get(f"/api/submissions/{retry_id}")
        assert failed_retry.status_code == 200

    student_id = (await student_client.get("/api/auth/me")).json()["id"]
    progress = db_session.get(StudentPracticeProgress, (student_id, problem_id))
    assert progress.valid_attempt_count == 2
    assert progress.retry_count == 1
    assert progress.wrong_answer_count == 1
    assert progress.first_passed_at is not None


async def test_assignment_submission_limit_reserves_queued_attempt(
    student_client,
    db_session,
):
    course_id = (await student_client.get("/api/courses")).json()["items"][0]["id"]
    assignment = (
        await student_client.get(f"/api/courses/{course_id}/assignments")
    ).json()["items"][0]
    item_data = assignment["items"][1]
    item = db_session.scalar(
        select(AssignmentItem).where(AssignmentItem.id == item_data["id"])
    )
    item.submission_limit = 1
    db_session.commit()

    payload = {
        "source_code": "def count_evens(values):\n    return 0\n",
        "problem_id": item_data["problem"]["id"],
        "assignment_item_id": item.id,
    }
    with patch(
        "app.routers.submissions.judge0_submit",
        return_value={"token": "reserved-token"},
    ) as mock_submit:
        first = await student_client.post("/api/submissions", json=payload)
        second = await student_client.post("/api/submissions", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "submission_limit_reached"
    mock_submit.assert_called_once()
