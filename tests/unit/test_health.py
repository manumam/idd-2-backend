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
    assert response.json() == {'listo': True, 'estado': {'mongodb': 'up'}}
    assert response.headers['X-Request-Id'] == 'ready-up'


@pytest.mark.parametrize('error', [None, RuntimeError('secret')])
def test_ready_ignores_redis_down(client, monkeypatch, error):
    pings = _mockear_pings(monkeypatch, caidas=('redis',), error=error)
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json() == {'listo': True, 'estado': {'mongodb': 'up'}}
    pings['redis'].assert_not_called()


@pytest.mark.parametrize('error', [None, RuntimeError('secret')])
def test_ready_503_when_mongodb_down(client, monkeypatch, error):
    pings = _mockear_pings(monkeypatch, caidas=('mongodb',), error=error)
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {'listo': False, 'estado': {'mongodb': 'down'}}
    assert 'secret' not in response.text
    pings['mongodb'].assert_called_once()
    assert client.get('/health').status_code == 200


@pytest.mark.parametrize('error', [None, RuntimeError('secret')])
def test_ready_ignores_influxdb_down_y_health_lo_informa(client, monkeypatch, error):
    pings = _mockear_pings(monkeypatch, caidas=('influxdb',), error=error)
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json() == {'listo': True, 'estado': {'mongodb': 'up'}}
    pings['influxdb'].assert_not_called()
    health = client.get('/health')
    assert health.status_code == 200
    assert health.json()['estado']['influxdb'] == 'down'


@pytest.fixture
def reloj(monkeypatch):
    from app.services import health_service
    ahora = [1000.0]
    monkeypatch.setattr(health_service.estado_fuentes, '_reloj', lambda: ahora[0])
    return ahora


def test_health_y_ready_reusan_el_ultimo_ping(client, monkeypatch, reloj):
    pings = _mockear_pings(monkeypatch)
    client.get('/health')
    client.get('/health')
    assert client.get('/ready').status_code == 200
    for ping in pings.values():
        ping.assert_called_once()


def test_solo_se_vuelve_a_hacer_ping_de_las_fuentes_vencidas(client, monkeypatch, reloj):
    pings = _mockear_pings(monkeypatch)
    client.get('/ready')
    reloj[0] += 10
    client.get('/health')
    assert [pings[n].call_count for n in ('mongodb', 'redis', 'influxdb')] == [1, 1, 1]

    reloj[0] += 5
    client.get('/health')
    assert [pings[n].call_count for n in ('mongodb', 'redis', 'influxdb')] == [2, 1, 1]


def test_ready_informa_la_caida_cuando_vence_el_ultimo_resultado(client, monkeypatch, reloj):
    pings = _mockear_pings(monkeypatch)
    assert client.get('/ready').status_code == 200
    pings['mongodb'].return_value = False

    reloj[0] += 14
    assert client.get('/ready').status_code == 200
    reloj[0] += 1
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json()['estado']['mongodb'] == 'down'
