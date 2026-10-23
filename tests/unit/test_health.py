from unittest.mock import Mock
import pytest
from app.services.health_service import FUENTES


def test_live_never_calls_dependencies(client, monkeypatch):
    mocks = []
    for adapter in FUENTES.values():
        operation = Mock(side_effect=AssertionError('No consultar dependencias en liveness'))
        monkeypatch.setattr(adapter, 'ping', operation)
        mocks.append(operation)
    assert client.get('/live').json() == {'estado': 'alive'}
    for operation in mocks:
        operation.assert_not_called()


def test_ready_all_dependencies_up(client, monkeypatch):
    for adapter in FUENTES.values():
        monkeypatch.setattr(adapter, 'ping', Mock(return_value=True))
    response = client.get('/ready', headers={'X-Request-Id': 'ready-up'})
    assert response.status_code == 200
    assert response.json() == {'listo': True, 'estado': {name: 'up' for name in FUENTES}}
    assert response.headers['X-Request-Id'] == 'ready-up'


@pytest.mark.parametrize('failure', [False, RuntimeError('secret')])
def test_ready_partial_failure_preserves_individual_states(client, monkeypatch, failure):
    for name, adapter in FUENTES.items():
        mock = Mock(return_value=True)
        if name == 'redis':
            mock = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
        monkeypatch.setattr(adapter, 'ping', mock)
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json()['listo'] is False
    assert response.json()['estado'] == {name: 'down' if name == 'redis' else 'up' for name in FUENTES}
    assert 'secret' not in response.text
    assert client.get('/health').status_code == 200
