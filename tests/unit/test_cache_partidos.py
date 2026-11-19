from unittest.mock import Mock

import pytest
from prometheus_client import REGISTRY
from pydantic import BaseModel

from app.adapters import redis_adapter
from app.config.settings import settings
from app.services.cache_partidos import clave_mapa_calor, guardar_cache, leer_cache


class Respuesta(BaseModel):
    valor: int


@pytest.fixture
def set_cache(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(redis_adapter, "set_cache", mock)
    return mock


def lecturas_cache(funcionalidad: str, resultado: str) -> float:
    return REGISTRY.get_sample_value(
        "api_cache_total", {"funcionalidad": funcionalidad, "resultado": resultado}
    ) or 0.0


def test_guardar_cache_sin_ttl_usa_el_ttl_configurado(set_cache):
    guardar_cache("partido:v2:P1", Respuesta(valor=1))

    set_cache.assert_called_once_with("partido:v2:P1", '{"valor":1}', settings.fixture_cache_ttl_seconds)


def test_guardar_cache_con_ttl_explicito_lo_pasa_a_redis(set_cache):
    guardar_cache("mapa_calor:v2:P1:J1:todo:todo", Respuesta(valor=1), ttl_segundos=600)

    set_cache.assert_called_once_with("mapa_calor:v2:P1:J1:todo:todo", '{"valor":1}', 600)


@pytest.mark.parametrize("ttl", [0, -5, 3601, 2.5, "60", True])
def test_guardar_cache_rechaza_ttl_invalido(set_cache, ttl):
    with pytest.raises(ValueError):
        guardar_cache("partido:v2:P1", Respuesta(valor=1), ttl_segundos=ttl)

    set_cache.assert_not_called()


def test_clave_mapa_calor_con_rango():
    assert clave_mapa_calor("P1", "J1", "10", "45") == "mapa_calor:v2:P1:J1:10:45"


def test_clave_mapa_calor_sin_rango_usa_token_fijo():
    assert clave_mapa_calor("P1", "J1") == "mapa_calor:v2:P1:J1:todo:todo"
    assert clave_mapa_calor("P1", "J1", hasta="45") == "mapa_calor:v2:P1:J1:todo:45"


def test_leer_cache_registra_mapa_calor_en_hit_y_miss(monkeypatch):
    get_cache = Mock(return_value=None)
    monkeypatch.setattr(redis_adapter, "get_cache", get_cache)
    miss, hit = lecturas_cache("mapa_calor", "miss"), lecturas_cache("mapa_calor", "hit")

    assert leer_cache(clave_mapa_calor("P1", "J1"), Respuesta) is None
    get_cache.return_value = '{"valor":7}'
    assert leer_cache(clave_mapa_calor("P1", "J1"), Respuesta) == Respuesta(valor=7)

    assert lecturas_cache("mapa_calor", "miss") == miss + 1
    assert lecturas_cache("mapa_calor", "hit") == hit + 1
