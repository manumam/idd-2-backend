"""Lecturas reales sobre los datos de los hitos anteriores, sin mocks."""
import os
import pytest

pytestmark = pytest.mark.integration
MODULES = set(os.getenv("LIVE_MODULES", "").split(","))
CASES = [
    ("mongodb", "/equipos/ARG", "codigo"),
    ("mongodb", "/jugadores?equipo=ARG&limit=2", "items"),
    ("mongodb", "/jugadores/ARG-10", "codigo"),
    ("neo4j", "/partidos/P-001", "codigo"),
    ("neo4j", "/partidos/P-001/eventos?limit=2", "items"),
    ("neo4j", "/sedes/S-04/goleadores?confederacion=CONMEBOL&limit=2", "items"),
    ("redis", "/sesiones/SES-DEMO", "sesionId"),
    ("influxdb", "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z", "items"),
    ("influxdb", "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z&ventana=1m", "items"),
]


@pytest.mark.parametrize("source,url,field", CASES)
def test_real_source(client, source, url, field):
    if source not in MODULES:
        pytest.skip("Configurar LIVE_MODULES y cargar datos representativos")
    response = client.get(url, headers={"X-Request-Id": "live-" + source})
    assert response.status_code == 200, response.text
    assert response.json()[field], "Se necesitan datos representativos; no alcanza una lista vacía"


def test_real_redis_delete_repeat(client):
    if "redis" not in MODULES:
        pytest.skip("Requiere Redis")
    from app.adapters import redis_adapter
    redis_adapter.client.hset("sesion:SES-HITO10TEST", mapping={"usuario_id": "U001"})
    assert client.get("/sesiones/SES-HITO10TEST").status_code == 200
    for _ in range(2):
        assert client.delete("/sesiones/SES-HITO10TEST").status_code == 204
    assert client.get("/sesiones/SES-HITO10TEST").status_code == 404
