from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_status_messages_cover_all_known_ids():
    from app.routers.submissions import get_status_message

    for status_id in range(1, 15):
        msg = get_status_message(status_id)
        assert isinstance(msg, str) and msg
        assert "Unknown" not in msg
    assert "Unknown" in get_status_message(999)


def test_enrich_result_does_not_mutate_input():
    from app.routers.submissions import _enrich_result

    original = {"token": "abc", "status": {"id": 3, "description": "Accepted"}}
    snapshot = {"token": "abc", "status": {"id": 3, "description": "Accepted"}}
    enriched = _enrich_result(original)
    assert original == snapshot
    assert enriched["done"] is True
    assert enriched["friendly_message"]
    assert enriched["poll_url"] == "/api/submissions/abc"


def test_create_validates_empty_source():
    r = client.post("/api/submissions", json={"source_code": ""})
    assert r.status_code == 422


def test_create_validates_limits():
    r = client.post(
        "/api/submissions",
        json={"source_code": "print(1)", "cpu_time_limit": 1000},
    )
    assert r.status_code == 422


def test_get_rejects_bad_token_without_calling_judge0():
    with patch("app.routers.submissions.judge0_get") as mock_get:
        r = client.get("/api/submissions/not-a-uuid")
        assert r.status_code == 422
        mock_get.assert_not_called()


def test_poll_flow_returns_token_then_done():
    token = "f83d50c3-bda9-437c-a396-8466b1f944b0"
    with patch("app.routers.submissions.judge0_submit", return_value={"token": token}):
        r = client.post("/api/submissions", json={"source_code": "print(42)"})
        assert r.status_code == 200
        body = r.json()
        assert body["token"] == token
        assert body["done"] is False
        assert body["poll_url"] == f"/api/submissions/{token}"

    with patch(
        "app.routers.submissions.judge0_get",
        return_value={
            "token": token,
            "status": {"id": 3, "description": "Accepted"},
            "stdout": "42\n",
        },
    ):
        r = client.get(f"/api/submissions/{token}")
        assert r.status_code == 200
        assert r.json()["done"] is True
