import pytest
import importlib.util
from pathlib import Path
import socket

spec = importlib.util.spec_from_file_location('diagnostico', Path('scripts/evaluar_conectividad.py'))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def test_failure_does_not_expose_secret():
    def fail():
        raise RuntimeError('mongodb://user:secret@localhost')
    result = diag.run_probe('mongodb', 'lectura', fail)
    assert result['estado'] == 'no_disponible'
    assert result['diagnostico'] == 'fallo_no_clasificado'
    assert 'secret' not in str(result)
    assert result['duracion_ms'] >= 0


def test_network_errors_have_distinct_diagnosis():
    assert diag.failure(socket.gaierror()) == 'host_no_resuelto'
    assert diag.failure(ConnectionRefusedError()) == 'conexion_rechazada'
    assert diag.failure(TimeoutError()) == 'timeout'


def test_api_non_success_is_not_healthy(monkeypatch):
    class Response:
        status_code = 503
        headers = {'X-Request-Id': 'example'}
    monkeypatch.setattr(diag.requests, 'get', lambda *args, **kwargs: Response())
    result = diag.api_probe('http://localhost', '/sesiones/SES-DEMO')
    assert result['estado'] == 'degradado'
    assert result['status_http'] == 503


@pytest.mark.parametrize('source', ['cassandra', 'iris'])
def test_restored_sources_have_network_and_read_probes(monkeypatch, source):
    from unittest.mock import Mock
    adapter = Mock()
    adapter.list_comentarios.return_value = []
    adapter.find_partido.return_value = None
    monkeypatch.setitem(diag.FUENTES, source, adapter)
    assert diag.target(source)[1] in (9042, 1972)
    result = diag.read_minimum(source)
    assert result == {'estado': 'disponible', 'resultado': 'sin_datos'}
    assert diag.ROUTES[source]
