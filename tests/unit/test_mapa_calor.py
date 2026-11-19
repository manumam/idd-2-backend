"""Mapa de calor: HTTP real con MongoDB, Redis e InfluxDB falsos."""
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.adapters import influx_adapter, mongo_adapter
from app.adapters.influx_adapter import SQL_MUESTRAS_POR_CELDA
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError
from app.services.grilla_cancha import parametros_grilla

URL = '/partidos/P-002/mapa-calor'
JUGADORES = {
    'ARG-10': dict(_id='ARG-10', equipo={'_id': 'ARG', 'nombre': 'Argentina'}),
    'BRA-10': dict(_id='BRA-10', equipo={'_id': 'BRA', 'nombre': 'Brasil'}),
}
CRUDO = [
    {'columna': 11.0, 'fila': 3.0, 'muestras': 30},
    {'columna': 20.0, 'fila': 13.0, 'muestras': 60},
]


class InfluxFalso:
    def __init__(self, filas=CRUDO):
        self.consultas = []
        self.filas = filas

    def query_sql(self, query, params=None, database=None):
        self.consultas.append((query, params, database))
        return self.filas


@pytest.fixture
def partido(monkeypatch, cache_redis):
    documento = dict(_id='P-002', fecha_hora=datetime(2030, 6, 9, 13), fase='Grupos', grupo='J',
                     local=dict(codigo='ARG', nombre='Argentina'), visitante=dict(codigo='JOR', nombre='Jordania'),
                     sede=None, estado='en_vivo', resultado=dict(goles_local=0, goles_visitante=0),
                     reloj=dict(periodo='primer_tiempo', minuto=30))
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(side_effect=lambda c: documento if c == 'P-002' else None))
    monkeypatch.setattr(mongo_adapter, 'find_jugador', Mock(side_effect=JUGADORES.get))
    monkeypatch.setattr(mongo_adapter, 'find_inicio_tracking', Mock(return_value=None))
    return documento


@pytest.fixture
def influx(monkeypatch):
    falso = InfluxFalso()
    monkeypatch.setattr(influx_adapter, 'query_sql', falso.query_sql)
    return falso


def test_en_vivo_cuenta_celdas_en_influx_hasta_el_minuto_del_reloj(client, partido, influx):
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == 200, response.text
    assert response.json() == {
        'partido': 'P-002', 'jugador': 'ARG-10', 'fuente': 'en_vivo',
        'grilla': {'largo_m': 105.0, 'ancho_m': 68.0, 'lado_m': 5.0, 'columnas': 21, 'filas': 14},
        'intervalo': {'desde_minuto': 0, 'hasta_minuto': 31},
        'celdas': [
            {'columna': 11, 'fila': 3, 'muestras': 30, 'intensidad': 0.5},
            {'columna': 20, 'fila': 13, 'muestras': 60, 'intensidad': 1.0},
        ],
    }
    assert influx.consultas == [(SQL_MUESTRAS_POR_CELDA, dict(
        parametros_grilla(), partido='P-002', jugador='ARG-10',
        desde='2030-06-09T13:00:00Z', hasta='2030-06-09T13:31:00Z'), settings.influx_database_en_vivo)]
    for nombre in ('partido', 'jugador', 'desde', 'hasta', *parametros_grilla()):
        assert f'${nombre}' in SQL_MUESTRAS_POR_CELDA
    assert 'AVG' not in SQL_MUESTRAS_POR_CELDA.upper()


def test_rango_explicito_anclado_al_inicio_del_tracking(client, partido, influx):
    mongo_adapter.find_inicio_tracking.return_value = datetime(2030, 6, 9, 15, 2, 40)
    response = client.get(URL, params={'jugador_id': 'ARG-10', 'desde_minuto': 10, 'hasta_minuto': 45})
    assert response.json()['intervalo'] == {'desde_minuto': 10, 'hasta_minuto': 45}
    params = influx.consultas[0][1]
    assert (params['desde'], params['hasta']) == ('2030-06-09T15:12:00Z', '2030-06-09T15:47:00Z')


def test_finalizado_sin_reloj_lee_todo_el_partido(client, partido, influx):
    partido.update(estado='finalizado', reloj=None)
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.json()['intervalo'] == {'desde_minuto': 0, 'hasta_minuto': 120}
    assert influx.consultas[0][1]['hasta'] == '2030-06-09T15:00:00Z'


def test_proximo_devuelve_celdas_vacias_sin_consultar_influx(client, partido, influx):
    partido.update(estado='proximo', resultado=None, reloj=None)
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == 200
    assert response.json()['celdas'] == [] and response.json()['fuente'] is None
    assert response.json()['intervalo'] is None
    assert influx.consultas == []


def test_sin_muestras_devuelve_celdas_vacias(client, partido, influx):
    influx.filas = []
    assert client.get(URL, params={'jugador_id': 'ARG-10'}).json()['celdas'] == []


@pytest.mark.parametrize('params', [
    {'jugador_id': 'ARG-10', 'desde_minuto': -1},
    {'jugador_id': 'ARG-10', 'hasta_minuto': 121},
    {'jugador_id': 'ARG-10', 'desde_minuto': 45, 'hasta_minuto': 45},
    {'jugador_id': 'ARG-10', 'desde_minuto': 50, 'hasta_minuto': 10},
    {'jugador_id': 'ARG-10', 'desde_minuto': 31},
    {'jugador_id': 'ARG-10', 'desde_minuto': 'x'},
    {'jugador_id': 'arg-10'},
    {},
])
def test_rangos_y_jugador_invalidos(client, partido, influx, params):
    response = client.get(URL, params=params)
    assert response.status_code == 400
    assert response.json()['code'] == 'VALIDACION_INVALIDA'
    assert influx.consultas == []


def test_rango_invertido_no_consulta_mongodb(client, partido, influx):
    client.get(URL, params={'jugador_id': 'ARG-10', 'desde_minuto': 50, 'hasta_minuto': 10})
    mongo_adapter.find_partido.assert_not_called()


@pytest.mark.parametrize('url,jugador,code', [
    ('/partidos/P-999/mapa-calor', 'ARG-10', 'PARTIDO_NO_ENCONTRADO'),
    (URL, 'BRA-10', 'JUGADOR_NO_ENCONTRADO'),
    (URL, 'ARG-99', 'JUGADOR_NO_ENCONTRADO'),
])
def test_partido_o_jugador_inexistente(client, partido, influx, url, jugador, code):
    response = client.get(url, params={'jugador_id': jugador})
    assert response.status_code == 404
    assert response.json()['code'] == code
    assert influx.consultas == []


@pytest.mark.parametrize('error,status,code', [
    (TimeoutError(), 504, 'INFLUXDB_TIMEOUT'),
    (ConnectionRefusedError(), 503, 'INFLUXDB_UNAVAILABLE'),
])
def test_influx_caido(client, partido, monkeypatch, error, status, code):
    monkeypatch.setattr(influx_adapter, 'query_sql', Mock(side_effect=DatabaseUnavailableError('InfluxDB', error)))
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == status
    assert response.json()['code'] == code
