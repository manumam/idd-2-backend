from unittest.mock import Mock

import pytest
import requests
from pymongo.errors import OperationFailure, NetworkTimeout
from redis.exceptions import AuthenticationError, AuthorizationError, TimeoutError

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
])
def test_driver_categories(error, category):
    assert classify_failure(error) == category
    wrapped = DatabaseUnavailableError('Redis', error)
    assert classify_failure(DatabaseUnavailableError('Redis', wrapped)) == category
    assert 'secret' not in wrapped.message


@pytest.mark.parametrize('error,status,suffix', [
    (NetworkTimeout('secret'), 504, 'TIMEOUT'),
    (OperationFailure('secret', code=18), 503, 'AUTHENTICATION_FAILED'),
    (OperationFailure('secret', code=13), 503, 'ACCESS_DENIED'),
    (OperationFailure('secret', code=26), 503, 'CONTEXT_UNAVAILABLE'),
    (OperationFailure('secret', code=2), 500, 'QUERY_FAILED'),
])
def test_http_error_contract(client, monkeypatch, caplog, error, status, suffix):
    # Inject at the driver's operation boundary, exercising adapter translation.
    monkeypatch.setattr(mongo_adapter, 'connect', Mock(side_effect=error))
    response = client.get('/equipos/ARG', headers={'X-Request-Id': 'failure-test'})
    assert response.status_code == status
    assert response.json()['code'] == f'MONGODB_{suffix}'
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

