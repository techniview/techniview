from uuid import uuid4

import pytest


def problem_payload():
    return {
        "title": "Draft",
        "prompt": "Return the input value.",
        "difficulty": "easy",
        "execution_mode": "call_based",
        "function_name": "solve",
        "starter_code": "def solve(value): pass",
        "canonical_solution": "def solve(value): return value",
        "tags": [],
        "test_cases": [
            {"input": "[1]", "expected_output": "1", "visibility": "public"}
        ],
    }


@pytest.mark.anyio
async def test_professor_can_copy_problem_and_hidden_cases_stay_redacted(
    teacher_client,
):
    copied = await teacher_client.post("/api/problems/1/copy")
    assert copied.status_code == 201, copied.text
    data = copied.json()
    assert data["origin"] == "custom"
    assert data["state"] == "draft"
    assert [case["case_order"] for case in data["test_cases"]] == [1, 2]
    assert "canonical_solution" not in data
    public = await teacher_client.get(f"/api/problems/{data['id']}")
    assert public.status_code == 200
    assert public.json()["test_count"] == 2
    assert len(public.json()["public_tests"]) == 1
    replacement = problem_payload()
    replacement["title"] = "Edited copied problem"
    replacement["test_cases"] = [
        {"input": "[[3, 4]]", "expected_output": "7", "visibility": "hidden"},
        {"input": "[[0]]", "expected_output": "0", "visibility": "public"},
    ]
    updated = await teacher_client.patch(
        f"/api/problems/{data['id']}", json=replacement
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Edited copied problem"
    assert [case["case_order"] for case in updated.json()["test_cases"]] == [1, 2]


@pytest.mark.anyio
async def test_student_cannot_use_authoring_and_professor_can_manage_private_sets(
    student_client, teacher_client
):
    denied = await student_client.post("/api/problems", json=problem_payload())
    assert denied.status_code == 403
    created = await teacher_client.post(
        "/api/question-sets", json={"title": "Week 1", "description": "Basics"}
    )
    assert created.status_code == 201, created.text
    qid = created.json()["id"]
    updated = await teacher_client.put(
        f"/api/question-sets/{qid}/items", json={"problem_ids": [1, 2]}
    )
    assert updated.status_code == 200, updated.text
    assert [i["problem"]["id"] for i in updated.json()["items"]] == [1, 2]
    assert (await student_client.get(f"/api/question-sets/{qid}")).status_code == 403
    draft = await teacher_client.post("/api/problems", json=problem_payload())
    assert draft.status_code == 201, draft.text
    updated = await teacher_client.put(
        f"/api/question-sets/{qid}/items",
        json={"problem_ids": [1, draft.json()["id"]]},
    )
    assert updated.status_code == 200, updated.text
    publish = await teacher_client.post(f"/api/question-sets/{qid}/publish")
    assert publish.status_code == 422


@pytest.mark.anyio
async def test_published_builtin_problem_cannot_be_edited_in_place(teacher_client):
    response = await teacher_client.patch("/api/problems/1", json=problem_payload())
    assert response.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("dispatch_before_edit", [False, True])
async def test_draft_edits_preserve_queued_and_running_case_snapshots(
    teacher_client, db_session, monkeypatch, dispatch_before_edit
):
    from app.models import Submission
    from app.worker.submissions import process_next_submission
    from sqlalchemy import text

    # SQLite leaves foreign keys off unless explicitly enabled.
    db_session.commit()
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    assert db_session.scalar(text("PRAGMA foreign_keys")) == 1
    original = problem_payload()
    original.update(cpu_time_limit_seconds=2, memory_limit_kb=64000)
    created = await teacher_client.post("/api/problems", json=original)
    problem_id = created.json()["id"]
    response = await teacher_client.post(
        f"/api/problems/{problem_id}/run",
        headers={"Idempotency-Key": uuid4().hex},
        json={"source_code": "def solve(value): return value"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    calls = []

    def submit(source, **kwargs):
        calls.append((source, kwargs))
        return {"token": "snapshot-token", "status": {"id": 1}}

    monkeypatch.setattr("app.worker.submissions.judge0_submit", submit)
    monkeypatch.setattr(
        "app.worker.submissions.judge0_get",
        lambda token: {"token": token, "status": {"id": 3}, "stdout": "1\n"},
    )
    if dispatch_before_edit:
        assert process_next_submission(db_session, "snapshot-test")
    replacement = problem_payload()
    replacement.update(
        function_name="new_function",
        starter_code="def new_function(value): pass",
        cpu_time_limit_seconds=10,
        memory_limit_kb=128000,
        test_cases=[{"input": "[99]", "expected_output": "99", "visibility": "public"}],
    )
    edited = await teacher_client.patch(f"/api/problems/{problem_id}", json=replacement)
    assert edited.status_code == 200, edited.text
    if not dispatch_before_edit:
        assert process_next_submission(db_session, "snapshot-test")
    assert len(calls) == 1
    source, options = calls[0]
    assert "__techniview_name = 'solve'" in source
    assert "__techniview_json.loads('[1]')" in source
    assert options["expected_output"] == "1"
    assert options["cpu_time_limit"] == 2
    assert options["memory_limit"] == 64000
    run = db_session.get(Submission, run_id)
    run.next_check_at = None
    for case_result in run.case_results:
        case_result.next_attempt_at = None
    db_session.commit()
    assert process_next_submission(db_session, "snapshot-test")
    result = await teacher_client.get(f"/api/submissions/{run_id}")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "passed"
    assert result.json()["public_results"][0]["input"] == "[1]"
    edited = await teacher_client.patch(f"/api/problems/{problem_id}", json=original)
    assert edited.status_code == 200, edited.text
