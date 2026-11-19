from unittest.mock import Mock
import pytest
from app.services.health_service import FUENTES


def _mockear_pings(monkeypatch, caidas=(), error=None):
    pings = {}
    for name, adapter in FUENTES.items():
        if name in caidas:
            ping = Mock(side_effect=error) if error else Mock(return_value=False)
        else:
            ping = Mock(return_value=True)
        monkeypatch.setattr(adapter, 'ping', ping)
        pings[name] = ping
    return pings


def test_live_never_calls_dependencies(client, monkeypatch):
    mocks = []
    for adapter in FUENTES.values():
        operation = Mock(side_effect=AssertionError('No consultar dependencias en liveness'))
        monkeypatch.setattr(adapter, 'ping', operation)
        mocks.append(operation)
    assert client.get('/live').json() == {'estado': 'alive'}
    for operation in mocks:
        operation.assert_not_called()


def test_health_lists_only_final_stack_sources(client, monkeypatch):
    _mockear_pings(monkeypatch, caidas=('redis',))
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'estado': {'mongodb': 'up', 'redis': 'down', 'influxdb': 'up'}}


def test_ready_all_essential_up(client, monkeypatch):
    _mockear_pings(monkeypatch)
    response = client.get('/ready', headers={'X-Request-Id': 'ready-up'})
    assert response.status_code == 200
    assert response.json() == {'listo': True, 'estado': {'mongodb': 'up', 'influxdb': 'up'}}
    assert response.headers['X-Request-Id'] == 'ready-up'


@pytest.mark.parametrize('error', [None, RuntimeError('secret')])
def test_ready_ignores_redis_down(client, monkeypatch, error):
    pings = _mockear_pings(monkeypatch, caidas=('redis',), error=error)
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json() == {'listo': True, 'estado': {'mongodb': 'up', 'influxdb': 'up'}}
    pings['redis'].assert_not_called()


@pytest.mark.parametrize('caida', ['mongodb', 'influxdb'])
@pytest.mark.parametrize('error', [None, RuntimeError('secret')])
def test_ready_503_when_essential_down(client, monkeypatch, caida, error):
    pings = _mockear_pings(monkeypatch, caidas=(caida,), error=error)
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json()['listo'] is False
    assert response.json()['estado'] == {name: 'down' if name == caida else 'up' for name in ('mongodb', 'influxdb')}
    assert 'secret' not in response.text
    for ping in (pings['mongodb'], pings['influxdb']):
        ping.assert_called_once()
    assert client.get('/health').status_code == 200
