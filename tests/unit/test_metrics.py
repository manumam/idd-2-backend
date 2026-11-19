from unittest.mock import Mock

from prometheus_client import REGISTRY, generate_latest

from app.adapters import mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.main import app


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
