"""Materialización de ocupación por celda y minuto, con InfluxDB y Redis falsos."""
from fnmatch import fnmatchcase
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from redis.exceptions import RedisError

from app.core.exceptions import DatabaseUnavailableError
from app.services.grilla_cancha import parametros_grilla

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('materializar_ocupacion', ROOT / 'scripts/materializar_ocupacion.py')
ocupacion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocupacion)

EN_VIVO, RESUMEN = 'fixture2030_en_vivo', 'fixture2030_resumen'
POR_MINUTO = [
    {'jugador_id': 'ARG-10', 'equipo_id': 'ARG', 'minuto': '2030-06-09T13:00:00', 'columna': 11.0, 'fila': 3.0, 'muestras': 13},
    {'jugador_id': 'ARG-10', 'equipo_id': 'ARG', 'minuto': '2030-06-09T13:01:00', 'columna': 11.0, 'fila': 3.0, 'muestras': 60},
    {'jugador_id': 'ARG-10', 'equipo_id': 'ARG', 'minuto': '2030-06-09T13:00:00', 'columna': 20.0, 'fila': 13.0, 'muestras': 47},
]
PARTIDO_COMPLETO = [
    {'jugador_id': 'ARG-10', 'columna': 11.0, 'fila': 3.0, 'muestras': 73},
    {'jugador_id': 'ARG-10', 'columna': 20.0, 'fila': 13.0, 'muestras': 47},
]


class InfluxFalso:
    def __init__(self, materializado=None):
        self.consultas = []
        self.materializado = materializado

    def query_sql(self, query, params=None, database=None):
        self.consultas.append((query, params, database))
        if query == ocupacion.SQL_OCUPACION:
            return POR_MINUTO
        if query == ocupacion.SQL_OCUPACION_PARTIDO:
            return PARTIDO_COMPLETO
        if self.materializado is None:
            raise DatabaseUnavailableError('InfluxDB', Exception('tabla inexistente'))
        return self.materializado


class RedisFalso:
    def __init__(self, claves):
        self.claves = set(claves)
        self.patrones = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def scan_iter(self, match, count):
        self.patrones.append(match)
        return [k for k in self.claves if fnmatchcase(k, match)]

    def keys(self, *_):
        raise AssertionError('KEYS bloquea Redis; usar SCAN')

    def delete(self, *claves):
        self.claves -= set(claves)


def test_parametros_de_la_consulta_salen_de_la_grilla():
    influx = InfluxFalso()
    ocupacion.leer_ocupacion(influx, EN_VIVO, 'P-002')
    assert influx.consultas == [(ocupacion.SQL_OCUPACION, dict(parametros_grilla(), partido='P-002'), EN_VIVO)]
    for nombre in ('partido', *parametros_grilla()):
        assert f'${nombre}' in ocupacion.SQL_OCUPACION


def test_line_protocol_con_celda_como_tag_y_muestras_enteras():
    assert ocupacion.linea_ocupacion('P-002', POR_MINUTO[0]) == (
        'ocupacion_jugador_minuto,partido_id=P-002,equipo_id=ARG,jugador_id=ARG-10,celda=11_3 '
        'muestras=13i 1907240400')


def test_tag_invalido_no_se_escribe():
    fila = dict(POR_MINUTO[0], jugador_id='ARG 10')
    with pytest.raises(ValueError):
        ocupacion.linea_ocupacion('P-002', fila)


def _materializar(influx, redis):
    lotes = []

    def escribir(base, lineas):
        lotes.append((base, lineas))
        return 0

    resultado = ocupacion.materializar(influx, escribir, lambda: redis, EN_VIVO, RESUMEN, 'P-002')
    return resultado, lotes


def test_reprocesar_escribe_el_mismo_lote_sin_sumar():
    redis = RedisFalso([])
    primero, lotes1 = _materializar(InfluxFalso(), redis)
    segundo, lotes2 = _materializar(InfluxFalso(), redis)
    assert lotes1 == lotes2 and lotes1[0][0] == RESUMEN
    assert primero == segundo == {'partido': 'P-002', 'enviadas': 3, 'rechazadas': 0}


def test_invalida_solo_los_mapas_del_partido_con_scan():
    redis = RedisFalso(['mapa_calor:v2:P-002:ARG-10:todo:todo', 'mapa_calor:v2:P-002:ARG-7:0:45',
                        'mapa_calor:v2:P-051:ARG-10:todo:todo', 'partido:v2:P-002'])
    _materializar(InfluxFalso(), redis)
    assert redis.patrones == ['mapa_calor:v2:P-002:*']
    assert redis.claves == {'mapa_calor:v2:P-051:ARG-10:todo:todo', 'partido:v2:P-002'}


def test_falla_de_redis_solo_advierte(capsys):
    def conectar():
        raise RedisError('caído')

    resultado = ocupacion.materializar(InfluxFalso(), lambda base, lineas: 0, conectar, EN_VIVO, RESUMEN, 'P-002')
    assert resultado['enviadas'] == 3
    assert 'Advertencia' in capsys.readouterr().err


def test_solo_validar_no_escribe_y_comprueba_la_suma_de_ventanas(monkeypatch, capsys):
    modulo_influx = sys.modules['app.adapters.influx_adapter']
    influx = InfluxFalso()
    escribir = MagicMock()
    monkeypatch.setattr(modulo_influx, 'influx_adapter', influx)
    monkeypatch.setattr(ocupacion.cargar_influx, 'escribir', escribir)
    monkeypatch.setattr(sys, 'argv', ['materializar_ocupacion.py', '--partido', 'P-002', '--solo-validar'])
    ocupacion.main()
    escribir.assert_not_called()
    assert all(q.startswith('SELECT') for q, _, _ in influx.consultas)
    assert json.loads(capsys.readouterr().out) == [{
        'partido': 'P-002', 'puntos': 3, 'series': 2, 'muestras': 120,
        'ventanas_suman_total': True, 'puntos_obsoletos': 0}]


def test_validar_detecta_ventanas_que_no_suman_y_puntos_obsoletos(monkeypatch):
    monkeypatch.setitem(PARTIDO_COMPLETO[0], 'muestras', 74)
    influx = InfluxFalso(materializado=[
        {'jugador_id': 'ARG-10', 'celda': '11_3', 'time': '2030-06-09T13:00:00'},
        {'jugador_id': 'ARG-10', 'celda': '5_5', 'time': '2030-06-09T13:00:00'},
    ])
    resultado = ocupacion.validar(influx, EN_VIVO, RESUMEN, 'P-002')
    assert resultado['ventanas_suman_total'] is False
    assert resultado['puntos_obsoletos'] == 1
