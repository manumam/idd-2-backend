"""HTTP real ASGI; adaptadores sustituidos para probar contratos sin motores."""
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import Mock

import pytest
from app.adapters import mongo_adapter, neo4j_adapter, redis_adapter, influx_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.main import app

EQUIPO = dict(_id="ARG", nombre="Argentina", confederacion="CONMEBOL", grupo="A",
              ranking_fifa=1, anfitrion=True)
JUGADOR = dict(_id="ARG-10", nombre="Jugador", apellido="Demo", dorsal=10, posicion="Delantero",
               equipo={"_id": "ARG", "nombre": "Argentina"}, fecha_nacimiento=datetime(2000, 1, 1))
PARTIDO = dict(id="P-001", fase="Grupos", grupo="A", fecha="2030-06-24", sede=None,
               local={"id": "ARG", "nombre": "Argentina"}, visitante=None)
SESION = dict(usuario_id="U001", nombre_usuario="Demo", rol="hincha", idioma="es",
              ultimo_acceso="2030-06-24T20:00:00Z", acciones=1, ttl_segundos=60)
PUNTO = dict(time="2030-06-24T20:00:00Z", equipo_id="ARG", posesion_pct=60,
             tiros_acumulados=2, pases_intervalo=10)
STATS = "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z"
CASES = [
    ("/equipos/ARG", mongo_adapter, "find_equipo", EQUIPO),
    ("/jugadores/ARG-10", mongo_adapter, "find_jugador", JUGADOR),
    ("/jugadores?equipo=ARG", mongo_adapter, "list_jugadores", [JUGADOR]),
    ("/partidos/P-001", neo4j_adapter, "find_partido", PARTIDO),
    ("/partidos/P-001/eventos", neo4j_adapter, "find_eventos", []),
    ("/sesiones/SES-DEMO", redis_adapter, "get_sesion", SESION),
    (STATS, influx_adapter, "find_estadisticas", [PUNTO]),
]


@pytest.mark.parametrize("url,adapter,method,data", CASES)
def test_success(client, monkeypatch, url, adapter, method, data):
    operation = Mock(return_value=data)
    monkeypatch.setattr(adapter, method, operation)
    response = client.get(url, headers={"X-Request-Id": "test-123"})
    assert response.status_code == 200, response.text
    assert response.headers["X-Request-Id"] == "test-123"
    operation.assert_called_once()


def test_goleadores(client, monkeypatch):
    monkeypatch.setattr(neo4j_adapter, "sede_existe", Mock(return_value=True))
    monkeypatch.setattr(neo4j_adapter, "find_goleadores", Mock(return_value=[dict(
        jugador_id="ARG-10", jugador_nombre="Jugador Demo", equipo_id="ARG",
        equipo_nombre="Argentina", partido="P-001", minuto=15)]))
    assert client.get("/sedes/S-04/goleadores?confederacion=CONMEBOL").json()["items"][0]["minuto"] == 15


@pytest.mark.parametrize("url,adapter,method,data", CASES)
def test_dependency_down(client, monkeypatch, url, adapter, method, data):
    source = {id(mongo_adapter): "MongoDB", id(neo4j_adapter): "Neo4j",
              id(redis_adapter): "Redis", id(influx_adapter): "InfluxDB"}[id(adapter)]
    monkeypatch.setattr(adapter, method, Mock(side_effect=DatabaseUnavailableError(source, RuntimeError("secret-token"))))
    response = client.get(url)
    assert response.status_code == 503
    assert response.json()["code"] == source.upper() + "_UNAVAILABLE"
    assert "secret-token" not in response.text
    assert set(response.json()) == {"code", "message", "requestId"}
    assert response.json()["requestId"] == response.headers["X-Request-Id"]


@pytest.mark.parametrize("url,adapter,method", [
    ("/equipos/ARG", mongo_adapter, "find_equipo"),
    ("/jugadores/ARG-10", mongo_adapter, "find_jugador"),
    ("/partidos/P-001", neo4j_adapter, "find_partido"),
    ("/partidos/P-001/eventos", neo4j_adapter, "find_eventos"),
    ("/sesiones/SES-EXPIRED", redis_adapter, "get_sesion"),
])
def test_not_found(client, monkeypatch, url, adapter, method):
    monkeypatch.setattr(adapter, method, Mock(return_value=None))
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("url", [
    "/equipos/arg", "/jugadores", "/jugadores?equipo=ARG&limit=101", "/jugadores?equipo=ARG&skip=-1",
    "/jugadores?equipo=ARG&posicion=Invalido", "/partidos/INVALID/eventos",
    "/sesiones/invalid",
    STATS.replace("20:05:00", "19:00:00"), STATS.replace("20:05:00", "21:00:00"),
    STATS.replace("20:05:00", "25:00:00"), STATS + "&ventana=10m",
])
def test_invalid_before_database(client, monkeypatch, url):
    operations = []
    for _, adapter, method, _ in CASES:
        mock = Mock(side_effect=AssertionError("La entrada inválida no debe consultar"))
        monkeypatch.setattr(adapter, method, mock)
        operations.append(mock)
    response = client.get(url)
    assert response.status_code == 400, response.text
    for operation in operations:
        operation.assert_not_called()


@pytest.mark.parametrize("url,adapter,method", [
    ("/jugadores?equipo=ARG", mongo_adapter, "list_jugadores"),
    (STATS, influx_adapter, "find_estadisticas"),
])
def test_valid_empty(client, monkeypatch, url, adapter, method):
    monkeypatch.setattr(adapter, method, Mock(return_value=[]))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_aggregation(client, monkeypatch):
    monkeypatch.setattr(influx_adapter, "find_estadisticas", Mock(return_value=[PUNTO, dict(
        PUNTO, time="2030-06-24T20:00:05Z", posesion_pct=40, tiros_acumulados=3, pases_intervalo=20)]))
    response = client.get(STATS + "&ventana=1m")
    assert response.json()["items"] == [dict(hora="2030-06-24T20:00:00Z", equipo="ARG", posesionPct=50, tiros=3, pasesIntervalo=30)]


def test_delete_idempotent(client, monkeypatch):
    operation = Mock()
    monkeypatch.setattr(redis_adapter, "delete_sesion", operation)
    for _ in range(2):
        response = client.delete("/sesiones/SES-DEMO")
        assert response.status_code == 204
        assert response.content == b""
    assert operation.call_count == 2


def test_health_all_sources(client, monkeypatch):
    from app.services.health_service import FUENTES
    for name, adapter in FUENTES.items():
        monkeypatch.setattr(adapter, "ping", Mock(return_value=True))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["estado"] == dict(mongodb="up", neo4j="up", redis="up", influxdb="up")


def test_openapi_matches_export(client):
    from pathlib import Path
    import yaml
    schema = client.get("/openapi.json").json()
    assert schema == yaml.safe_load(Path("openapi/openapi.yaml").read_text())
    for path in schema["paths"].values():
        for operation in path.values():
            assert "422" not in operation["responses"]
            for response in operation["responses"].values():
                assert "X-Request-Id" in response["headers"]
    assert app.openapi()["info"]["version"] == "1.0.0"


def test_safe_internal_error(client, monkeypatch, caplog):
    monkeypatch.setattr(mongo_adapter, "find_equipo", Mock(side_effect=RuntimeError("secret-token")))
    response = client.get("/equipos/ARG", headers={"X-Request-Id": "safe-id"})
    assert response.status_code == 500
    assert response.json()["requestId"] == "safe-id"
    assert "secret-token" not in response.text
    assert "secret-token" not in caplog.text


@pytest.mark.parametrize("method,url,status", [("get", "/inexistente", 404), ("post", "/equipos/ARG", 405)])
def test_framework_errors(client, method, url, status):
    response = getattr(client, method)(url)
    assert response.status_code == status
    assert set(response.json()) == {"code", "message", "requestId"}


def test_postman_operations_and_parameters_match_openapi():
    import json
    import re
    from pathlib import Path
    collection = json.loads(Path('postman_collection.json').read_text())
    operations = {}
    def walk(items):
        for item in items:
            if 'item' in item:
                walk(item['item'])
            if 'request' not in item:
                continue
            request = item['request']
            path = request['url']['raw'].replace('{{baseUrl}}', '').split('?')[0]
            path = re.sub(r'\{\{codigo(?:Equipo|Jugador|Partido|Sede)\}\}', '{codigo}', path)
            path = path.replace('{{sesionId}}', '{sesionId}')
            key = (path, request['method'].lower())
            assert key not in operations
            operations[key] = item
    walk(collection['item'])
    schema = app.openapi()
    assert set(operations) == {(path, method) for path, methods in schema['paths'].items() for method in methods}
    for (path, method), item in operations.items():
        expected = {p['name'] for p in schema['paths'][path][method].get('parameters', []) if p['in'] == 'query'}
        assert expected == {p['key'] for p in item['request']['url'].get('query', [])}
        if path not in ('/health', '/live', '/ready'):
            assert 504 in {response['code'] for response in item['response']}
            assert '504' in schema['paths'][path][method]['responses']
