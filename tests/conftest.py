from fnmatch import fnmatchcase
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.adapters import redis_adapter
from app.main import app
from app.services import health_service


@pytest.fixture(autouse=True)
def estado_fuentes_sin_resultados(monkeypatch):
    """Cada test empieza sin pings previos: /health y /ready reusan resultados durante 15 s."""
    monkeypatch.setattr(health_service.estado_fuentes, '_estados', {})
    monkeypatch.setattr(health_service.estado_fuentes, '_evaluado_en', {})


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def cache_redis(monkeypatch):
    """Redis en memoria: GET, SET con TTL, DEL y borrado por patrón (SCAN + DEL)."""
    cache = {}

    def borrar_patron(patron):
        for key in [k for k in cache if fnmatchcase(k, patron)]:
            del cache[key]

    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=cache.get))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock(side_effect=lambda k, v, t: cache.update({k: v})))
    monkeypatch.setattr(redis_adapter, 'delete_cache', Mock(side_effect=lambda k: cache.pop(k, None)))
    monkeypatch.setattr(redis_adapter, 'delete_cache_matching', Mock(side_effect=borrar_patron))
    return cache
