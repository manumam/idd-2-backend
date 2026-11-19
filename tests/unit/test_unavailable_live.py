"""Falla de red real de Redis, sin sustituir su driver ni su adaptador."""
from unittest.mock import Mock

from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import settings
from app.adapters import mongo_adapter, redis_adapter


def test_redis_caido_no_interrumpe_la_lectura(monkeypatch):
    redis_adapter.close()
    monkeypatch.setattr(settings, "redis_host", "127.0.0.1")
    monkeypatch.setattr(settings, "redis_port", 1)
    monkeypatch.setattr(settings, "db_timeout_seconds", 0.2)
    monkeypatch.setattr(mongo_adapter, "list_fixture", Mock(return_value=[]))
    with TestClient(app) as client:
        response = client.get("/fixture", headers={"X-Request-Id": "real-down"})
    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert response.headers["X-Request-Id"] == "real-down"
