import pytest

pytestmark = pytest.mark.anyio


async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["api"] == "/api"


async def test_api_root(client):
    r = await client.get("/api")
    assert r.status_code == 200
    assert "health" in r.json()


async def test_ping(client):
    r = await client.get("/api/ping")
    assert r.status_code == 200
    assert r.json() == {"pong": True}


async def test_protected_routes_require_authentication(client):
    assert (await client.get("/api/problems")).status_code == 401
    assert (await client.get("/api/me/analytics")).status_code == 401
