"""Mapa de calor: HTTP real con MongoDB, Redis e InfluxDB falsos."""
from datetime import datetime
from unittest.mock import Mock

import pytest
import requests
from prometheus_client import REGISTRY

from app.adapters import influx_adapter, mongo_adapter, redis_adapter
from app.adapters.influx_adapter import SQL_MUESTRAS_POR_CELDA, SQL_OCUPACION_POR_CELDA
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


MATERIALIZADO = [
    {'celda': '11_3', 'muestras': 30},
    {'celda': '20_13', 'muestras': 60},
    {'celda': '99_1', 'muestras': 5},
]


def rechazo_influx(texto):
    respuesta = requests.Response()
    respuesta.status_code = 400
    respuesta._content = texto.encode()
    return DatabaseUnavailableError('InfluxDB', requests.HTTPError(response=respuesta))


class InfluxFalso:
    def __init__(self, filas=CRUDO, ocupacion=MATERIALIZADO):
        self.consultas = []
        self.filas = filas
        self.ocupacion = ocupacion

    def query_sql(self, query, params=None, database=None):
        self.consultas.append((query, params, database))
        if query == SQL_OCUPACION_POR_CELDA:
            if self.ocupacion is None:
                raise rechazo_influx("Error during planning: table 'public.iox.ocupacion_jugador_minuto' not found")
            return self.ocupacion
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


def test_finalizado_lee_la_ocupacion_materializada(client, partido, influx):
    partido.update(estado='finalizado', reloj=None)
    response = client.get(URL, params={'jugador_id': 'ARG-10', 'desde_minuto': 0, 'hasta_minuto': 45})
    data = response.json()
    assert data['fuente'] == 'historico'
    assert data['celdas'] == [
        {'columna': 11, 'fila': 3, 'muestras': 30, 'intensidad': 0.5},
        {'columna': 20, 'fila': 13, 'muestras': 60, 'intensidad': 1.0},
    ]
    assert influx.consultas == [(SQL_OCUPACION_POR_CELDA, dict(
        partido='P-002', jugador='ARG-10', desde='2030-06-09T13:00:00Z', hasta='2030-06-09T13:45:00Z'),
        settings.influx_database)]
    assert 'AVG' not in SQL_OCUPACION_POR_CELDA.upper()


def test_finalizado_sin_reloj_lee_todo_el_partido(client, partido, influx):
    partido.update(estado='finalizado', reloj=None)
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.json()['intervalo'] == {'desde_minuto': 0, 'hasta_minuto': 120}
    assert influx.consultas[0][1]['hasta'] == '2030-06-09T15:00:00Z'


@pytest.mark.parametrize('ocupacion', [[], None])
def test_finalizado_sin_materializar_usa_el_crudo(client, partido, influx, ocupacion):
    partido.update(estado='finalizado')
    influx.ocupacion = ocupacion
    data = client.get(URL, params={'jugador_id': 'ARG-10'}).json()
    assert data['fuente'] == 'en_vivo' and len(data['celdas']) == 2
    assert [c[0] for c in influx.consultas] == [SQL_OCUPACION_POR_CELDA, SQL_MUESTRAS_POR_CELDA]


def test_en_vivo_no_lee_la_ocupacion_materializada(client, partido, influx):
    client.get(URL, params={'jugador_id': 'ARG-10'})
    assert [c[0] for c in influx.consultas] == [SQL_MUESTRAS_POR_CELDA]


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


@pytest.mark.parametrize('estado', ['en_vivo', 'finalizado'])
@pytest.mark.parametrize('ausencia', ['tabla', 'base'])
def test_sin_tracking_devuelve_vacio_sin_ocultar_error_de_consulta(
    client, partido, monkeypatch, estado, ausencia
):
    partido['estado'] = estado
    def post(url, **kwargs):
        payload = kwargs['json']
        tabla = 'ocupacion_jugador_minuto' if 'ocupacion_jugador_minuto' in payload['q'] else 'tracking_jugador'
        respuesta = requests.Response()
        if ausencia == 'base':
            import json
            respuesta.status_code = 404
            respuesta._content = json.dumps({'error': 'query error: database not found: ' + payload['db']}).encode()
        else:
            respuesta.status_code = 400
            respuesta._content = f"Error during planning: table 'public.iox.{tabla}' not found".encode()
        return respuesta
    monkeypatch.setattr(influx_adapter, 'get_session', lambda: Mock(post=post))
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == 200
    assert response.json()['celdas'] == []


@pytest.mark.parametrize('status,texto,esperado', [
    (401, 'unauthorized', 503),
    (403, 'forbidden', 503),
    (404, 'ruta no encontrada', 503),
    (400, "Error during planning: table 'otra_tabla' not found", 500),
    (400, 'Schema error: No field named x_m', 500),
])
def test_ausencia_opcional_no_oculta_otras_fallas(client, partido, monkeypatch, status, texto, esperado):
    respuesta = requests.Response()
    respuesta.status_code = status
    respuesta._content = texto.encode()
    monkeypatch.setattr(influx_adapter, 'get_session', lambda: Mock(post=Mock(return_value=respuesta)))
    assert client.get(URL, params={'jugador_id': 'ARG-10'}).status_code == esperado


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


def test_error_de_consulta_del_historico_no_cae_al_crudo(client, partido, influx, monkeypatch):
    partido['estado'] = 'finalizado'
    def rechazar(query, params=None, database=None):
        if query == SQL_OCUPACION_POR_CELDA:
            raise rechazo_influx('Schema error: No field named muestras_mal')
        return CRUDO
    monkeypatch.setattr(influx_adapter, 'query_sql', rechazar)
    response = client.get('/partidos/P-002/mapa-calor', params={'jugador_id': 'ARG-10'})
    assert response.status_code == 500
    assert response.json()['code'] == 'INFLUXDB_QUERY_FAILED'


def lecturas_cache(resultado):
    return REGISTRY.get_sample_value(
        'api_cache_total', {'funcionalidad': 'mapa_calor', 'resultado': resultado}) or 0.0


@pytest.mark.parametrize('estado,ocupacion,fuente,ttl', [
    ('en_vivo', MATERIALIZADO, 'en_vivo', 5),
    ('finalizado', MATERIALIZADO, 'historico', 3600),
    ('finalizado', [], 'en_vivo', 5),
])
def test_miss_consulta_influx_y_guarda_con_ttl_segun_fuente(client, partido, influx, cache_redis, estado,
                                                            ocupacion, fuente, ttl):
    partido['estado'] = estado
    influx.ocupacion = ocupacion
    misses = lecturas_cache('miss')
    data = client.get(URL, params={'jugador_id': 'ARG-10', 'desde_minuto': 0, 'hasta_minuto': 45}).json()
    assert data['fuente'] == fuente
    assert lecturas_cache('miss') == misses + 1
    guardados = [(c.args[0], c.args[2]) for c in redis_adapter.set_cache.call_args_list
                 if c.args[0].startswith('mapa_calor:')]
    assert guardados == [('mapa_calor:v2:P-002:ARG-10:0:45', ttl)]


def test_hit_no_consulta_influx(client, partido, influx, cache_redis):
    primera = client.get(URL, params={'jugador_id': 'ARG-10'}).json()
    consultas = len(influx.consultas)
    hits = lecturas_cache('hit')
    assert client.get(URL, params={'jugador_id': 'ARG-10'}).json() == primera
    assert len(influx.consultas) == consultas
    assert lecturas_cache('hit') == hits + 1
    assert 'mapa_calor:v2:P-002:ARG-10:todo:todo' in cache_redis


def test_la_clave_distingue_jugador_y_rango(client, partido, influx, cache_redis):
    for params in ({}, {'desde_minuto': 0}, {'hasta_minuto': 31}, {'desde_minuto': 0, 'hasta_minuto': 31}):
        client.get(URL, params={'jugador_id': 'ARG-10', **params})
    assert len(influx.consultas) == 4
    assert {k for k in cache_redis if k.startswith('mapa_calor:')} == {
        'mapa_calor:v2:P-002:ARG-10:todo:todo', 'mapa_calor:v2:P-002:ARG-10:0:todo',
        'mapa_calor:v2:P-002:ARG-10:todo:31', 'mapa_calor:v2:P-002:ARG-10:0:31'}


def test_proximo_no_se_cachea(client, partido, influx, cache_redis):
    partido.update(estado='proximo', resultado=None, reloj=None)
    client.get(URL, params={'jugador_id': 'ARG-10'})
    assert not any(k.startswith('mapa_calor:') for k in cache_redis)


def test_cache_invalida_recalcula(client, partido, influx, cache_redis):
    cache_redis['mapa_calor:v2:P-002:ARG-10:todo:todo'] = '{invalido'
    errores = lecturas_cache('error')
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == 200 and len(response.json()['celdas']) == 2
    assert lecturas_cache('error') == errores + 1
    assert len(influx.consultas) == 1


def test_redis_caido_no_falla_el_pedido(client, partido, influx, monkeypatch):
    caido = Mock(side_effect=DatabaseUnavailableError('Redis', ConnectionRefusedError()))
    for operacion in ('get_cache', 'set_cache'):
        monkeypatch.setattr(redis_adapter, operacion, caido)
    response = client.get(URL, params={'jugador_id': 'ARG-10'})
    assert response.status_code == 200 and len(response.json()['celdas']) == 2
    assert len(influx.consultas) == 1
