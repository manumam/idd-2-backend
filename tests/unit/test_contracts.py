"""HTTP real ASGI; adaptadores sustituidos para probar contratos sin motores."""
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import Mock

import pytest
from app.adapters import mongo_adapter, neo4j_adapter, cassandra_adapter, redis_adapter, influx_adapter, iris_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.main import app

EQUIPO = dict(_id="ARG", nombre="Argentina", confederacion="CONMEBOL", grupo="A",
              ranking_fifa=1, anfitrion=True)
JUGADOR = dict(_id="ARG-10", nombre="Jugador", apellido="Demo", dorsal=10, posicion="Delantero",
               equipo={"_id": "ARG", "nombre": "Argentina"}, fecha_nacimiento=datetime(2000, 1, 1))
PARTIDO = dict(id="P-001", fase="Grupos", grupo="A", fecha="2030-06-24", sede=None,
               local={"id": "ARG", "nombre": "Argentina"}, visitante=None)
COMENTARIO = dict(comentario_id=UUID("ba894580-ec17-11f5-8123-0242ac120002"), usuario_id="U001",
                  nombre_usuario="Demo", idioma="es", texto="Vamos", estado_moderacion="APROBADO")
SESION = dict(usuario_id="U001", nombre_usuario="Demo", rol="hincha", idioma="es",
              ultimo_acceso="2030-06-24T20:00:00Z", acciones=1, ttl_segundos=60)
PUNTO = dict(time="2030-06-24T20:00:00Z", equipo_id="ARG", posesion_pct=60,
             tiros_acumulados=2, pases_intervalo=10)
OBJETO = dict(id="1", codigo="P-001", estado="Finalizado",
              eventos=[dict(id="1", tipo="Gol", minuto=15, partidoId="1")])
STATS = "/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z"
COMMENTS = "/partidos/ARG-ESP-20300624/comentarios?bloque=2030-06-24T20:05:00Z"
CASES = [
    ("/equipos/ARG", mongo_adapter, "find_equipo", EQUIPO),
    ("/jugadores/ARG-10", mongo_adapter, "find_jugador", JUGADOR),
    ("/jugadores?equipo=ARG", mongo_adapter, "list_jugadores", [JUGADOR]),
    ("/partidos/P-001", neo4j_adapter, "find_partido", PARTIDO),
    ("/partidos/P-001/eventos", neo4j_adapter, "find_eventos", []),
    (COMMENTS, cassandra_adapter, "list_comentarios", [COMENTARIO]),
    ("/sesiones/SES-DEMO", redis_adapter, "get_sesion", SESION),
    (STATS, influx_adapter, "find_estadisticas", [PUNTO]),
    ("/objetos/partidos/1", iris_adapter, "find_partido", OBJETO),
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
    source = {id(mongo_adapter): "MongoDB", id(neo4j_adapter): "Neo4j", id(cassandra_adapter): "Cassandra",
              id(redis_adapter): "Redis", id(influx_adapter): "InfluxDB", id(iris_adapter): "IRIS"}[id(adapter)]
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
    ("/objetos/partidos/1", iris_adapter, "find_partido"),
])
def test_not_found(client, monkeypatch, url, adapter, method):
    monkeypatch.setattr(adapter, method, Mock(return_value=None))
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("url", [
    "/equipos/arg", "/jugadores", "/jugadores?equipo=ARG&limit=101", "/jugadores?equipo=ARG&skip=-1",
    "/jugadores?equipo=ARG&posicion=Invalido", "/partidos/INVALID/eventos",
    "/sesiones/invalid", "/objetos/partidos/0", "/objetos/partidos/1?skip=1001",
    COMMENTS.replace("20:05:00", "20:06:00"), COMMENTS.replace("2030-06-24", "2030-02-30"),
    COMMENTS + "&cursor=not-a-uuid", COMMENTS + "&cursor=550e8400-e29b-41d4-a716-446655440000",
    COMMENTS.replace("ARG-ESP-20300624", "P-001"), COMMENTS + "&limit=0",
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
    (COMMENTS, cassandra_adapter, "list_comentarios"), (STATS, influx_adapter, "find_estadisticas"),
])
def test_valid_empty(client, monkeypatch, url, adapter, method):
    monkeypatch.setattr(adapter, method, Mock(return_value=[]))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_cursor_and_partition(client, monkeypatch):
    older = dict(COMENTARIO, comentario_id=UUID("11424f80-ec17-11f5-8123-0242ac120002"))
    operation = Mock(side_effect=[[COMENTARIO, older], [older]])
    monkeypatch.setattr(cassandra_adapter, "list_comentarios", operation)
    first = client.get(COMMENTS + "&limit=1").json()
    assert first["siguienteCursor"] == str(COMENTARIO["comentario_id"])
    second = client.get(COMMENTS + "&limit=1&cursor=" + first["siguienteCursor"]).json()
    assert second["siguienteCursor"] is None
    assert second["items"][0]["comentarioId"] != first["items"][0]["comentarioId"]
    assert operation.call_args.args == ("ARG-ESP-20300624", datetime(2030, 6, 24, 20, 5, tzinfo=timezone.utc), 2, COMENTARIO["comentario_id"])


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
        monkeypatch.setattr(adapter, "ping", Mock(side_effect=DatabaseUnavailableError(name)) if name == "iris" else Mock(return_value=True))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["estado"] == dict(mongodb="up", neo4j="up", cassandra="up", redis="up", influxdb="up", iris="down")


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
