from unittest.mock import Mock, MagicMock

import pytest
from pymongo.errors import ConnectionFailure
from redis.exceptions import ConnectionError as RedisConnectionError
import requests

from app.adapters.mongo_adapter import MongoAdapter
from app.adapters.redis_adapter import RedisAdapter
from app.adapters.influx_adapter import InfluxAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError


@pytest.mark.parametrize("adapter,method,args,error", [
    (MongoAdapter(), "find_equipo", ["ARG"], ConnectionFailure("hidden")),
    (RedisAdapter(), "get_cache", ["fixture:v1:todos"], RedisConnectionError("hidden")),
])
def test_native_driver_failure_is_503(monkeypatch, adapter, method, args, error):
    name = "get_client" if isinstance(adapter, RedisAdapter) else "connect"
    monkeypatch.setattr(adapter, name, Mock(side_effect=error))
    with pytest.raises(DatabaseUnavailableError) as caught:
        getattr(adapter, method)(*args)
    assert caught.value.status_code == 503


def test_influx_parameters_and_failure(monkeypatch):
    adapter = InfluxAdapter()
    session = Mock()
    monkeypatch.setattr(adapter, "get_session", lambda: session)
    monkeypatch.setattr(adapter, "_resolve_token", lambda: None)
    session.post.side_effect = requests.Timeout("secret-token")
    with pytest.raises(DatabaseUnavailableError):
        adapter.find_estadisticas("P-001", "start", "end", "ARG", 5000)
    payload = session.post.call_args.kwargs["json"]
    assert payload["params"] == dict(partido="P-001", desde="start", hasta="end", equipo="ARG")
    assert "P-001" not in payload["q"]
    assert session.post.call_args.kwargs["timeout"] > 0
    assert payload["db"] == settings.influx_database


def _adapter_con_respuesta(monkeypatch):
    adapter = InfluxAdapter()
    session = Mock()
    session.post.return_value = Mock(status_code=200, json=Mock(return_value=[]))
    monkeypatch.setattr(adapter, "get_session", lambda: session)
    monkeypatch.setattr(adapter, "_resolve_token", lambda: None)
    return adapter, session


def test_influx_consulta_en_base_en_vivo(monkeypatch):
    adapter, session = _adapter_con_respuesta(monkeypatch)
    adapter.query_sql("SELECT x_m FROM tracking_jugador WHERE partido_id = $p", {"p": "P-001"},
                      database=settings.influx_database_en_vivo)
    payload = session.post.call_args.kwargs["json"]
    assert payload["db"] == settings.influx_database_en_vivo
    assert payload["params"] == {"p": "P-001"}
    assert "P-001" not in payload["q"]


def test_influx_rechaza_base_no_configurada(monkeypatch):
    adapter, session = _adapter_con_respuesta(monkeypatch)
    with pytest.raises(ValueError):
        adapter.query_sql("SELECT 1", database="otra_base")
    session.post.assert_not_called()


def test_redis_borrado_por_patron_usa_scan():
    adapter = RedisAdapter()
    adapter._client = Mock()
    adapter._client.scan_iter.return_value = iter(["eventos:v2:P-001:50:0", "eventos:v2:P-001:1:1"])
    adapter.delete_cache_matching("eventos:v2:P-001:*")
    adapter._client.scan_iter.assert_called_once_with(match="eventos:v2:P-001:*", count=100)
    adapter._client.delete.assert_called_once_with("eventos:v2:P-001:50:0", "eventos:v2:P-001:1:1")
    adapter._client.keys.assert_not_called()
    adapter._client.scan_iter.return_value = iter([])
    adapter.delete_cache_matching("eventos:v2:P-002:*")
    adapter._client.delete.assert_called_once()
    adapter._client.scan_iter.side_effect = RedisConnectionError("hidden")
    with pytest.raises(DatabaseUnavailableError):
        adapter.delete_cache_matching("eventos:v2:P-001:*")


def test_adapter_logs_without_driver_message(monkeypatch, caplog):
    import logging
    adapter = MongoAdapter()
    monkeypatch.setattr(adapter, "connect", Mock(side_effect=ConnectionFailure("secret-token")))
    with caplog.at_level(logging.INFO), pytest.raises(DatabaseUnavailableError):
        adapter.find_equipo("ARG")
    assert "dependency=MongoDB" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "secret-token" not in caplog.text


def test_catalogo_equipos_lee_mongo_sin_depender_del_fixture():
    adapter = MongoAdapter()
    adapter._client = Mock()
    adapter._db = MagicMock()
    cursor = adapter._db['equipos'].find.return_value
    cursor.sort.return_value = [{'_id': 'ARG', 'nombre': 'Argentina'}]
    assert adapter.list_equipos() == [{'_id': 'ARG', 'nombre': 'Argentina'}]
    adapter._db['equipos'].find.assert_called_once_with({}, {'_id': 1, 'nombre': 1})
    cursor.sort.assert_called_once_with([('nombre', 1), ('_id', 1)])


def test_tracking_usa_base_cruda_y_parametros(monkeypatch):
    from app.config.settings import settings
    adapter = InfluxAdapter()
    session = Mock()
    monkeypatch.setattr(adapter, 'get_session', lambda: session)
    monkeypatch.setattr(adapter, '_resolve_token', lambda: None)
    response = Mock(status_code=200)
    response.json.side_effect = [[{'table_name': 'tracking_jugador'}], []]
    session.post.return_value = response
    assert adapter.find_tracking_jugador('P-001', 'ARG-10', 'ARG', 'inicio', 'fin') == []
    payload = session.post.call_args.kwargs['json']
    assert payload['db'] == settings.influx_tracking_database
    assert payload['params'] == dict(partido='P-001', jugador='ARG-10', equipo='ARG', desde='inicio', hasta='fin')
    assert 'ARG-10' not in payload['q'] and 'LIMIT 14402' in payload['q']


def test_publicacion_individual_no_apunta_a_filas_parciales():
    adapter = MongoAdapter()
    adapter._client = Mock()
    adapter._db = MagicMock()
    coleccion = adapter._db['estadisticas_jugador_partido']
    coleccion.insert_many.side_effect = ConnectionFailure('fallo de escritura')
    with pytest.raises(DatabaseUnavailableError):
        adapter.publicar_resumenes_jugadores('P-001', {}, {'generacion': 'g'}, [{'_id': 'fila'}])
    adapter._db['partidos'].update_one.assert_not_called()
    coleccion.insert_many.side_effect = None
    adapter._db['partidos'].update_one.return_value.matched_count = 0
    assert not adapter.publicar_resumenes_jugadores('P-001', {'eventos': ['original']}, {'generacion': 'g'}, [{'_id': 'fila'}])
    filtro, actualizacion = adapter._db['partidos'].update_one.call_args.args
    assert filtro['eventos'] == ['original'] and 'tracking_control' in filtro and 'alineaciones' in filtro
    assert actualizacion == {'$set': {'jugadores_finales': {'generacion': 'g'}}}


def _respuesta(status):
    respuesta = requests.Response()
    respuesta.status_code = status
    return respuesta


def _adapter_escritura(monkeypatch, *respuestas, token=None):
    adapter = InfluxAdapter()
    session = Mock()
    session.post.side_effect = [r if isinstance(r, Exception) else _respuesta(r) for r in respuestas]
    monkeypatch.setattr(adapter, "get_session", lambda: session)
    monkeypatch.setattr(adapter, "_resolve_token", lambda: token)
    return adapter, session


def test_influx_escribe_en_lotes_atomicos_con_precision_en_segundos(monkeypatch):
    from app.adapters.influx_adapter import LOTE_LINEAS
    adapter, session = _adapter_escritura(monkeypatch, 204, 204, token="secreto")
    lineas = [f"tracking_pelota,partido_id=P-001 x_m=1.00 {i}" for i in range(LOTE_LINEAS + 1)]
    assert adapter.escribir_lineas(settings.influx_database_en_vivo, lineas) == 0
    assert session.post.call_count == 2
    url, = session.post.call_args.args
    kwargs = session.post.call_args.kwargs
    assert url.endswith("/api/v3/write_lp")
    assert kwargs["params"] == {"db": settings.influx_database_en_vivo, "precision": "second",
                                "accept_partial": "false", "no_sync": "false"}
    assert kwargs["headers"]["Authorization"] == "Bearer secreto"
    assert kwargs["data"].decode().count("\n") == 1


def test_influx_reintenta_solo_fallas_de_disponibilidad(monkeypatch):
    from app.adapters.influx_adapter import INTENTOS_POR_LOTE
    adapter, session = _adapter_escritura(
        monkeypatch, requests.ConnectionError("hidden"), 503, 204)
    assert adapter.escribir_lineas(settings.influx_database, ["a 1", "b 1"]) == 0
    assert session.post.call_count == 3
    adapter, session = _adapter_escritura(monkeypatch, *[500] * INTENTOS_POR_LOTE)
    assert adapter.escribir_lineas(settings.influx_database, ["a 1", "b 1"]) == 2
    assert session.post.call_count == INTENTOS_POR_LOTE
    adapter, session = _adapter_escritura(monkeypatch, 400)
    assert adapter.escribir_lineas(settings.influx_database, ["linea invalida"]) == 1
    assert session.post.call_count == 1


def test_influx_escritura_mide_latencia_y_errores(monkeypatch):
    from app.core import observability
    errores, duraciones = [], []
    monkeypatch.setattr(observability, "record_dependencia_error", lambda f, c: errores.append((f, c)))
    monkeypatch.setattr(observability, "record_dependencia", lambda f, o, s: duraciones.append((f, o)))
    adapter, _ = _adapter_escritura(monkeypatch, 204, 400)
    adapter.escribir_lineas(settings.influx_database, ["a 1"])
    adapter.escribir_lineas(settings.influx_database, ["b 1"])
    assert duraciones == [("influxdb", "escribir_lote")] * 2
    assert errores == [("influxdb", "query")]


def test_influx_escritura_rechaza_base_no_configurada(monkeypatch):
    adapter, session = _adapter_escritura(monkeypatch)
    with pytest.raises(ValueError):
        adapter.escribir_lineas("otra_base", ["a 1"])
    with pytest.raises(ValueError):
        adapter.escribir_lote(settings.influx_tracking_database + "_otra", ["a 1"])
    session.post.assert_not_called()
