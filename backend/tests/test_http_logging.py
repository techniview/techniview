import json
import subprocess
import sys
from pathlib import Path


def test_production_logging_emits_one_json_event_per_request():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio
import json
import logging

import httpx
import uvicorn

config = uvicorn.Config('main:app', access_log=False)
config.load()
assert logging.getLogger().getEffectiveLevel() == logging.WARNING
from app.core.observability import configure_logging
from main import app
configure_logging()

@app.get('/logging-test/{callback_token}')
def logging_test(callback_token: str):
    return {'ok': True}

async def request():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://test'
    ) as client:
        response = await client.get('/api/ping?token=private-query-value')
        assert response.status_code == 200
        print(json.dumps({'response_request_id': response.headers['X-Request-ID']}))
        response = await client.get('/logging-test/private-callback-token')
        assert response.status_code == 200

asyncio.run(request())
""",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    records = [json.loads(line) for line in result.stdout.splitlines()]
    events = [record for record in records if record.get("event") == "http_request"]
    assert len(events) == 2
    event = events[0]
    assert event["request_id"] == records[1]["response_request_id"]
    assert event["route"] == "/api/ping"
    assert event["status"] == 200
    assert event["method"] == "GET"
    assert event["duration_seconds"] >= 0
    assert "private-query-value" not in result.stdout + result.stderr
    assert events[1]["route"] == "/logging-test/{callback_token}"
    assert "private-callback-token" not in result.stdout + result.stderr


def test_unknown_http_methods_share_one_metrics_series():
    from app.core.observability import HttpMetrics

    registry = HttpMetrics()
    for index in range(100):
        registry.observe(f"CUSTOM{index}", "unmatched", 405, 0.01)
    payload = registry.render()
    requests = [
        line
        for line in payload.splitlines()
        if line.startswith("techniview_http_requests_total{")
    ]
    assert requests == [
        'techniview_http_requests_total{method="OTHER",'
        'route="unmatched",status="405"} 100'
    ]
    assert "CUSTOM" not in payload
