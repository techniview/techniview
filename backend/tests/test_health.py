from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["api"] == "/api"


def test_api_root():
    r = client.get("/api")
    assert r.status_code == 200
    assert "health" in r.json()


def test_ping():
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"pong": True}


def test_stub_routes():
    # TODO: replace with DB-backed tests when models land
    assert client.get("/api/problems").status_code == 200
    assert client.get("/api/stats/me").status_code == 200
