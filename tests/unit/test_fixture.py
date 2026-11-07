"""Contrato, Cache-Aside y degradación del listado del Mundial 2030."""
from datetime import datetime
from unittest.mock import Mock

import pytest
from pymongo.errors import NetworkTimeout

from app.adapters import mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.fixture import FixtureResponse
from app.services.fixture_service import FIXTURE_CACHE_KEY, invalidar_fixture


def partido(codigo='P-001', estado='proximo', resultado=None):
    return dict(_id=codigo, fecha_hora=datetime(2030, 6, 8, 18), fase='Grupos', grupo='H',
                local=dict(codigo='URU', nombre='Uruguay'), visitante=None,
                estado=estado, resultado=resultado)


@pytest.fixture
def operations(monkeypatch):
    from app.config.settings import settings
    monkeypatch.setattr(settings, 'fixture_cache_ttl_seconds', 5)
    mocks = {}
    for adapter, method, value in (
        (mongo_adapter, 'list_fixture', [partido()]),
        (redis_adapter, 'get_cache', None), (redis_adapter, 'set_cache', None),
        (redis_adapter, 'delete_cache', None),
    ):
        mocks[method] = Mock(return_value=value)
        monkeypatch.setattr(adapter, method, mocks[method])
    return mocks


def test_miss_then_hit_and_request_id(client, operations):
    first = client.get('/fixture', headers={'X-Request-Id': 'first'})
    assert first.status_code == 200
    assert first.json()['items'][0]['fecha_hora'] == '2030-06-08T18:00:00Z'
    key, payload, ttl = operations['set_cache'].call_args.args
    assert key == FIXTURE_CACHE_KEY and ttl == 5
    assert 'requestId' not in payload
    operations['get_cache'].return_value = payload
    second = client.get('/fixture', headers={'X-Request-Id': 'second'})
    assert second.json() == first.json()
    assert second.headers['X-Request-Id'] == 'second'
    operations['list_fixture'].assert_called_once()


@pytest.mark.parametrize('cached', ['{', '{}', '{"items":[{}]}'])
def test_invalid_cache_reconstructed(client, operations, cached):
    operations['get_cache'].return_value = cached
    assert client.get('/fixture').status_code == 200
    operations['list_fixture'].assert_called_once()
    operations['set_cache'].assert_called_once()


def test_redis_down_does_not_fail_read(client, operations):
    for name in ('get_cache', 'set_cache'):
        operations[name].side_effect = DatabaseUnavailableError('Redis')
    assert client.get('/fixture').status_code == 200


def test_empty(client, operations):
    operations['list_fixture'].return_value = []
    assert client.get('/fixture').json() == {'items': []}


@pytest.mark.parametrize('error,status,code', [
    (DatabaseUnavailableError('MongoDB'), 503, 'MONGODB_UNAVAILABLE'),
    (DatabaseUnavailableError('MongoDB', NetworkTimeout('hidden')), 504, 'MONGODB_TIMEOUT'),
])
def test_mongo_failure_not_cached(client, operations, error, status, code):
    operations['list_fixture'].side_effect = error
    response = client.get('/fixture')
    assert response.status_code == status
    assert response.json()['code'] == code
    assert response.json()['requestId'] == response.headers['X-Request-Id']
    operations['set_cache'].assert_not_called()


def test_valid_cache_survives_mongo_failure(client, operations):
    operations['get_cache'].return_value = '{"items":[]}'
    operations['list_fixture'].side_effect = DatabaseUnavailableError('MongoDB')
    assert client.get('/fixture').json() == {'items': []}
    operations['list_fixture'].assert_not_called()


def test_states_and_penalties(client, operations):
    operations['list_fixture'].return_value = [partido(), partido('P-002', 'en_vivo', dict(
        goles_local=1, goles_visitante=0)), partido('P-003', 'finalizado', dict(
        goles_local=2, goles_visitante=2, penales=dict(goles_local=4, goles_visitante=3)))]
    items = client.get('/fixture').json()['items']
    assert [p['estado'] for p in items] == ['proximo', 'en_vivo', 'finalizado']
    assert items[0]['resultado'] is None and items[0]['visitante'] is None
    assert items[2]['resultado']['goles_local'] == 2
    assert items[2]['resultado']['penales']['goles_local'] == 4


def test_invalid_state_result_not_accepted_from_cache():
    from pydantic import ValidationError
    p = partido()
    p['codigo'] = p.pop('_id')
    p['resultado'] = dict(goles_local=0, goles_visitante=0)
    with pytest.raises(ValidationError):
        FixtureResponse(items=[p])


def test_invalidation_optional(operations):
    assert invalidar_fixture()
    operations['delete_cache'].assert_called_once_with(FIXTURE_CACHE_KEY)
    operations['delete_cache'].side_effect = DatabaseUnavailableError('Redis')
    assert not invalidar_fixture()


def test_non_utf8_cache_is_a_miss(client, operations):
    operations['get_cache'].side_effect = UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid')
    assert client.get('/fixture').status_code == 200
    operations['list_fixture'].assert_called_once()
