from unittest.mock import Mock, MagicMock

import pytest
from pymongo.errors import ConnectionFailure
from redis.exceptions import ConnectionError as RedisConnectionError
import requests

from app.adapters.mongo_adapter import MongoAdapter
from app.adapters.redis_adapter import RedisAdapter
from app.adapters.influx_adapter import InfluxAdapter
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
