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
