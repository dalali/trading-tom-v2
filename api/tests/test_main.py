"""Smoke test: the app imports and serves /health without touching a
live DB (architecture 8.1 — migrations/bootstrap happen in start.sh,
not at app import/startup time).
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
