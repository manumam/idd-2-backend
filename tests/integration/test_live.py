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
    ("cassandra", "/partidos/ARG-ESP-20300624/comentarios?bloque=2030-06-24T20:05:00Z&limit=1", "items"),
    ("redis", "/sesiones/SES-DEMO", "sesionId"),
    ("influxdb", "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z", "items"),
    ("influxdb", "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z&ventana=1m", "items"),
    ("iris", "/objetos/partidos/" + os.getenv("IRIS_TEST_ID", "1"), "eventos"),
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


def test_real_cassandra_cursor(client):
    if "cassandra" not in MODULES:
        pytest.skip("Requiere dos comentarios en la ventana")
    url = "/partidos/ARG-ESP-20300624/comentarios?bloque=2030-06-24T20:05:00Z&limit=1"
    response = client.get(url)
    assert response.status_code == 200
    first = response.json()
    assert first["siguienteCursor"]
    response = client.get(url + "&cursor=" + first["siguienteCursor"])
    assert response.status_code == 200
    second = response.json()
    assert second["items"]
    assert second["items"][0]["comentarioId"] != first["items"][0]["comentarioId"]
