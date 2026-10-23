from unittest.mock import Mock

import pytest
import requests
from pymongo.errors import OperationFailure, NetworkTimeout
from redis.exceptions import AuthenticationError, AuthorizationError, TimeoutError
from neo4j.exceptions import Neo4jError

from app.adapters import mongo_adapter, redis_adapter
from app.adapters.influx_adapter import InfluxAdapter
from app.core.exceptions import DatabaseUnavailableError
from app.core.dependency_failures import classify_failure


@pytest.mark.parametrize('error,category', [
    (NetworkTimeout('secret'), 'timeout'),
    (TimeoutError('secret'), 'timeout'),
    (AuthenticationError('secret'), 'authentication'),
    (AuthorizationError('secret'), 'authorization'),
    (OperationFailure('secret', code=18), 'authentication'),
    (OperationFailure('secret', code=13), 'authorization'),
    (OperationFailure('secret', code=26), 'context'),
    (OperationFailure('secret', code=2), 'query'),
    (Neo4jError._hydrate_neo4j(code='Neo.ClientError.Database.DatabaseNotFound', message='secret'), 'context'),
    (Neo4jError._hydrate_neo4j(code='Neo.ClientError.Security.Forbidden', message='secret'), 'authorization'),
])
def test_driver_categories(error, category):
    assert classify_failure(error) == category
    wrapped = DatabaseUnavailableError('Redis', error)
    assert classify_failure(DatabaseUnavailableError('Redis', wrapped)) == category
    assert 'secret' not in wrapped.message


@pytest.mark.parametrize('error,status,suffix', [
    (TimeoutError('secret'), 504, 'TIMEOUT'),
    (AuthenticationError('secret'), 503, 'AUTHENTICATION_FAILED'),
    (AuthorizationError('secret'), 503, 'ACCESS_DENIED'),
    (OperationFailure('secret', code=26), 503, 'CONTEXT_UNAVAILABLE'),
    (OperationFailure('secret', code=2), 500, 'QUERY_FAILED'),
])
def test_http_error_contract(client, monkeypatch, caplog, error, status, suffix):
    # Inject at the driver's operation boundary, exercising adapter translation.
    driver = Mock()
    driver.hgetall.side_effect = error
    if isinstance(error, OperationFailure):
        monkeypatch.setattr(mongo_adapter, 'connect', Mock(side_effect=error))
        response = client.get('/equipos/ARG', headers={'X-Request-Id': 'failure-test'})
        source = 'MONGODB'
    else:
        monkeypatch.setattr(redis_adapter, 'get_client', lambda: driver)
        response = client.get('/sesiones/SES-DEMO', headers={'X-Request-Id': 'failure-test'})
        source = 'REDIS'
    assert response.status_code == status
    assert response.json()['code'] == f'{source}_{suffix}'
    assert response.json()['requestId'] == response.headers['X-Request-Id'] == 'failure-test'
    assert 'secret' not in response.text + caplog.text


@pytest.mark.parametrize('native_status,status,suffix', [
    (401, 503, 'AUTHENTICATION_FAILED'), (403, 503, 'ACCESS_DENIED'),
    (404, 503, 'CONTEXT_UNAVAILABLE'), (400, 500, 'QUERY_FAILED'),
    (500, 503, 'UNAVAILABLE'),
])
def test_influx_status_mapping(monkeypatch, native_status, status, suffix):
    adapter = InfluxAdapter()
    response = requests.Response()
    response.status_code = native_status
    session = Mock()
    session.post.return_value = response
    monkeypatch.setattr(adapter, 'get_session', lambda: session)
    monkeypatch.setattr(adapter, '_resolve_token', lambda: None)
    with pytest.raises(DatabaseUnavailableError) as caught:
        adapter.query_sql('SELECT 1')
    assert caught.value.status_code == status
    assert caught.value.code == 'INFLUXDB_' + suffix


def test_health_keeps_down_on_timeout(client, monkeypatch):
    from app.services.health_service import FUENTES
    for adapter in FUENTES.values():
        monkeypatch.setattr(adapter, 'ping', lambda: True)
    monkeypatch.setattr(redis_adapter, 'ping', Mock(side_effect=DatabaseUnavailableError('Redis', TimeoutError())))
    assert client.get('/health').json()['estado']['redis'] == 'down'


def test_neo4j_missing_database_through_adapter(client, monkeypatch):
    from app.adapters import neo4j_adapter
    error = Neo4jError._hydrate_neo4j(code='Neo.ClientError.Database.DatabaseNotFound', message='secret')
    monkeypatch.setattr(neo4j_adapter, 'get_driver', Mock(side_effect=error))
    response = client.get('/partidos/P-001')
    assert response.status_code == 503
    assert response.json()['code'] == 'NEO4J_CONTEXT_UNAVAILABLE'
    assert 'secret' not in response.text
