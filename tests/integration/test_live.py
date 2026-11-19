"""Lecturas reales sobre los datos de los hitos anteriores, sin mocks."""
import os
import pytest

pytestmark = pytest.mark.integration
MODULES = set(os.getenv("LIVE_MODULES", "").split(","))
CASES = [
    ("mongodb", "/equipos/ARG", "codigo"),
    ("mongodb", "/jugadores?equipo=ARG&limit=2", "items"),
    ("mongodb", "/jugadores/ARG-10", "codigo"),
    ("mongodb", "/partidos/P-001", "codigo"),
    ("mongodb", "/partidos/P-001/eventos?limit=2", "items"),
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

