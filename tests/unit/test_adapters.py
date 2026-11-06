from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
from uuid import UUID

import pytest
from cassandra.cluster import NoHostAvailable
from neo4j.exceptions import ServiceUnavailable
from pymongo.errors import ConnectionFailure
from redis.exceptions import ConnectionError as RedisConnectionError
import requests

from app.adapters.cassandra_adapter import CassandraAdapter
from app.adapters.neo4j_adapter import Neo4jAdapter
from app.adapters.mongo_adapter import MongoAdapter
from app.adapters.redis_adapter import RedisAdapter
from app.adapters.influx_adapter import InfluxAdapter
from app.adapters.iris_adapter import IrisAdapter
from app.core.exceptions import DatabaseUnavailableError


def test_cassandra_partition_and_cursor():
    adapter = CassandraAdapter()
    adapter._session = Mock()
    adapter._session.execute.return_value = []
    bloque = datetime(2030, 6, 24, 20, 5, tzinfo=timezone.utc)
    cursor = UUID("ba894580-ec17-11f5-8123-0242ac120002")
    adapter.list_comentarios("ARG-ESP-20300624", bloque, 21, cursor)
    query, params = adapter._session.execute.call_args.args
    assert "partido_id = %s AND bloque_temporal = %s" in query
    assert "comentario_id < %s" in query
    assert "ALLOW FILTERING" not in query
    assert params == ["ARG-ESP-20300624", bloque, cursor, 21]
    assert "20300624" not in query


@pytest.mark.parametrize("adapter,method,args,error", [
    (MongoAdapter(), "find_equipo", ["ARG"], ConnectionFailure("hidden")),
    (RedisAdapter(), "get_sesion", ["SES-DEMO"], RedisConnectionError("hidden")),
    (CassandraAdapter(), "list_comentarios", ["ARG-ESP-20300624", datetime.now(), 20], NoHostAvailable("hidden", {})),
    (Neo4jAdapter(), "find_partido", ["P-001"], ServiceUnavailable("hidden")),
])
def test_native_driver_failure_is_503(monkeypatch, adapter, method, args, error):
    name = "get_driver" if isinstance(adapter, Neo4jAdapter) else "get_client" if isinstance(adapter, RedisAdapter) else "connect"
    monkeypatch.setattr(adapter, name, Mock(side_effect=error))
    with pytest.raises(DatabaseUnavailableError) as caught:
        getattr(adapter, method)(*args)
    assert caught.value.status_code == 503


def test_neo4j_query_has_timeout(monkeypatch):
    adapter = Neo4jAdapter()
    driver = MagicMock()
    monkeypatch.setattr(adapter, "get_driver", lambda: driver)
    adapter._run("RETURN $id AS id", id="P-001")
    query, params = driver.session.return_value.__enter__.return_value.run.call_args.args
    assert query.timeout > 0
    assert params == {"id": "P-001"}


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


def test_redis_expiration_and_private_fields():
    adapter = RedisAdapter()
    adapter._client = Mock()
    adapter._client.hgetall.return_value = {"usuario_id": "U001", "acciones": "3", "ip_publica": "private"}
    adapter._client.ttl.return_value = -2
    assert adapter.get_sesion("SES-DEMO") is None
    adapter._client.ttl.return_value = -1
    result = adapter.get_sesion("SES-DEMO")
    assert result["ttl_segundos"] is None
    assert result["acciones"] == 3
    assert "ip_publica" not in result


def test_iris_projection_and_parent_relation(monkeypatch):
    import iris.dbapi
    connection = Mock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = (1, "P-001", "Finalizado")
    cursor.fetchall.return_value = [(2, "Gol", 15, 1)]
    monkeypatch.setattr(iris.dbapi, "connect", Mock(return_value=connection))
    result = IrisAdapter().find_partido(1, 20, 0)
    assert result["eventos"][0]["partidoId"] == "1"
    assert cursor.execute.call_args.args[1] == [1]
    cursor.setQueryTimeout.assert_called_once()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()


def test_adapter_logs_without_driver_message(monkeypatch, caplog):
    import logging
    adapter = MongoAdapter()
    monkeypatch.setattr(adapter, "connect", Mock(side_effect=ConnectionFailure("secret-token")))
    with caplog.at_level(logging.INFO), pytest.raises(DatabaseUnavailableError):
        adapter.find_equipo("ARG")
    assert "dependency=MongoDB" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "secret-token" not in caplog.text
