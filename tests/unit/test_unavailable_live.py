"""Falla de red real, sin sustituir el driver ni el adaptador."""
from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import settings
from app.adapters import redis_adapter


def test_real_connection_refused(monkeypatch):
    redis_adapter.close()
    monkeypatch.setattr(settings, "redis_host", "127.0.0.1")
    monkeypatch.setattr(settings, "redis_port", 1)
    monkeypatch.setattr(settings, "db_timeout_seconds", 0.2)
    with TestClient(app) as client:
        response = client.get("/sesiones/SES-DEMO", headers={"X-Request-Id": "real-down"})
    assert response.status_code == 503
    assert response.json()["code"] == "REDIS_UNAVAILABLE"
    assert response.json()["requestId"] == "real-down"
