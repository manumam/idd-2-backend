from unittest.mock import MagicMock, Mock

import pytest
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from pymongo.errors import NetworkTimeout

from app.adapters import mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.core.metrics import EstadoFuentesCollector
from app.main import app
from app.services.health_service import FUENTES


@pytest.fixture(autouse=True)
def pings(monkeypatch):
    mocks = {nombre: Mock(return_value=nombre != "redis") for nombre in FUENTES}
    for nombre, adapter in FUENTES.items():
        monkeypatch.setattr(adapter, "ping", mocks[nombre])
    return mocks


def requests_contados(ruta: str) -> float:
    return REGISTRY.get_sample_value(
        "api_http_requests_total", {"ruta": ruta, "metodo": "GET", "status": "200"}
    ) or 0.0


def test_metrics_expone_requests_y_latencia(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "api_http_requests_total" in response.text
    assert "api_latency_seconds" in response.text


def test_ruta_con_parametro_se_cuenta_por_plantilla(client, monkeypatch):
    monkeypatch.setattr(redis_adapter, "get_cache", Mock(return_value=None))
    monkeypatch.setattr(redis_adapter, "set_cache", Mock())
    monkeypatch.setattr(mongo_adapter, "find_equipo", Mock(return_value=dict(
        _id="ARG", nombre="Argentina", confederacion="CONMEBOL", grupo="A", ranking_fifa=1, anfitrion=True)))
    antes = requests_contados("/equipos/{codigo}")

    assert client.get("/equipos/ARG").status_code == 200

    assert requests_contados("/equipos/{codigo}") == antes + 1
    assert requests_contados("/equipos/ARG") == 0.0
    assert REGISTRY.get_sample_value("api_latency_seconds_count", {"ruta": "/equipos/{codigo}"}) >= 1


def test_ruta_inexistente_usa_etiqueta_fija(client):
    client.get("/no-existe-123")
    assert REGISTRY.get_sample_value(
        "api_http_requests_total", {"ruta": "sin_ruta", "metodo": "GET", "status": "404"}
    ) >= 1
    assert "/no-existe-123" not in client.get("/metrics").text


def test_metrics_no_se_cuenta_a_si_mismo(client):
    client.get("/metrics")
    assert requests_contados("/metrics") == 0.0


def test_metrics_fuera_del_contrato_openapi():
    assert "/metrics" not in app.openapi()["paths"]


def test_error_interno_se_cuenta_con_status_500(client, monkeypatch):
    monkeypatch.setattr(redis_adapter, "get_cache", Mock(return_value=None))
    monkeypatch.setattr(mongo_adapter, "find_equipo", Mock(side_effect=RuntimeError("falla")))
    etiquetas = {"ruta": "/equipos/{codigo}", "metodo": "GET", "status": "500"}
    antes = REGISTRY.get_sample_value("api_http_requests_total", etiquetas) or 0.0

    assert client.get("/equipos/ARG").status_code == 500

    assert REGISTRY.get_sample_value("api_http_requests_total", etiquetas) == antes + 1


def lecturas_cache(funcionalidad: str, resultado: str) -> float:
    return REGISTRY.get_sample_value(
        "api_cache_total", {"funcionalidad": funcionalidad, "resultado": resultado}
    ) or 0.0


def test_cache_fixture_cuenta_miss_y_hit(client, cache_redis, monkeypatch):
    monkeypatch.setattr(mongo_adapter, "list_fixture", Mock(return_value=[]))
    miss, hit = lecturas_cache("fixture", "miss"), lecturas_cache("fixture", "hit")

    client.get("/fixture")
    client.get("/fixture")

    assert lecturas_cache("fixture", "miss") == miss + 1
    assert lecturas_cache("fixture", "hit") == hit + 1


def test_cache_por_funcionalidad_sin_codigos_en_etiquetas(monkeypatch):
    from app.schemas.grupos import PosicionesResponse
    from app.services.cache_partidos import clave_posiciones, leer_cache
    get_cache = Mock(return_value=None)
    monkeypatch.setattr(redis_adapter, "get_cache", get_cache)
    antes = {resultado: lecturas_cache("posiciones", resultado) for resultado in ("hit", "miss", "error")}

    leer_cache(clave_posiciones("A"), PosicionesResponse)
    get_cache.return_value = "{"
    leer_cache(clave_posiciones("A"), PosicionesResponse)
    get_cache.side_effect = DatabaseUnavailableError("Redis")
    leer_cache(clave_posiciones("A"), PosicionesResponse)

    assert lecturas_cache("posiciones", "miss") == antes["miss"] + 1
    assert lecturas_cache("posiciones", "error") == antes["error"] + 2
    assert lecturas_cache("posiciones", "hit") == antes["hit"]
    assert "grupos:v2:A" not in generate_latest().decode()


def valor(nombre: str, etiquetas: dict) -> float:
    return REGISTRY.get_sample_value(nombre, etiquetas) or 0.0


def test_falla_de_dependencia_registra_latencia_y_un_solo_error(client, monkeypatch):
    monkeypatch.setattr(redis_adapter, "get_cache", Mock(return_value=None))
    monkeypatch.setattr(mongo_adapter, "connect", Mock(side_effect=DatabaseUnavailableError("MongoDB", NetworkTimeout())))
    latencia = {"fuente": "mongodb", "operacion": "find_equipo"}
    error = {"fuente": "mongodb", "categoria": "timeout"}
    latencias, errores = valor("api_dependencia_seconds_count", latencia), valor("api_dependencia_errores_total", error)

    assert client.get("/equipos/ARG").status_code == 504

    assert valor("api_dependencia_seconds_count", latencia) == latencias + 1
    assert valor("api_dependencia_errores_total", error) == errores + 1
    texto = client.get("/metrics").text
    assert "api_dependencia_seconds_bucket" in texto and "api_dependencia_errores_total" in texto


def test_dependencia_up_reutiliza_health_sin_nuevo_ping(client, pings):
    client.get("/health")

    assert valor("api_dependencia_up", {"fuente": "mongodb"}) == 1.0
    assert valor("api_dependencia_up", {"fuente": "redis"}) == 0.0
    assert valor("api_dependencia_up", {"fuente": "influxdb"}) == 1.0
    for ping in pings.values():
        ping.assert_called_once()


def test_dependencia_up_solo_reevalua_fuentes_vencidas():
    ahora = [100.0]
    evaluar = Mock(side_effect=lambda fuentes: {f: "up" for f in fuentes})
    collector = EstadoFuentesCollector(evaluar, ("mongodb", "redis"), 15, reloj=lambda: ahora[0])
    registry = CollectorRegistry()
    registry.register(collector)
    evaluar.assert_not_called()

    collector.registrar({"mongodb": "down"})
    assert registry.get_sample_value("api_dependencia_up", {"fuente": "mongodb"}) == 0.0
    evaluar.assert_called_once_with(("redis",))

    ahora[0] += 14
    registry.get_sample_value("api_dependencia_up", {"fuente": "mongodb"})
    evaluar.assert_called_once()

    ahora[0] += 1
    assert registry.get_sample_value("api_dependencia_up", {"fuente": "mongodb"}) == 1.0
    assert evaluar.call_count == 2


def test_pool_mongodb_cuenta_conexiones_tomadas_y_devueltas():
    from app.adapters.mongo_adapter import ConexionesEnUsoListener
    listener = ConexionesEnUsoListener()
    antes = valor("api_pool_conexiones_en_uso", {"fuente": "mongodb"})

    listener.connection_checked_out(Mock())
    listener.connection_checked_out(Mock())
    assert valor("api_pool_conexiones_en_uso", {"fuente": "mongodb"}) == antes + 2
    listener.connection_checked_in(Mock())
    listener.pool_cleared(Mock())

    assert valor("api_pool_conexiones_en_uso", {"fuente": "mongodb"}) == antes + 1
    listener.connection_checked_in(Mock())


def test_cliente_mongodb_registra_listener_del_pool(monkeypatch):
    import sys
    from app.adapters.mongo_adapter import ConexionesEnUsoListener, MongoAdapter
    cliente = MagicMock()
    monkeypatch.setattr(sys.modules["app.adapters.mongo_adapter"], "MongoClient", cliente)

    MongoAdapter().connect()

    listeners = cliente.call_args.kwargs["event_listeners"]
    assert [type(listener) for listener in listeners] == [ConexionesEnUsoListener]


def test_operaciones_en_curso_suben_durante_la_llamada_y_bajan_al_terminar():
    from app.core.observability import observe
    observado = {}

    @observe("Redis")
    def operacion():
        observado["durante"] = valor("api_dependencia_en_curso", {"fuente": "redis"})

    antes = valor("api_dependencia_en_curso", {"fuente": "redis"})
    operacion()

    assert observado["durante"] == antes + 1
    assert valor("api_dependencia_en_curso", {"fuente": "redis"}) == antes


def test_operaciones_en_curso_bajan_aunque_la_operacion_falle():
    from app.core.observability import observe

    @observe("InfluxDB")
    def operacion():
        raise NetworkTimeout("timeout")

    antes = valor("api_dependencia_en_curso", {"fuente": "influxdb"})
    with pytest.raises(NetworkTimeout):
        operacion()

    assert valor("api_dependencia_en_curso", {"fuente": "influxdb"}) == antes
