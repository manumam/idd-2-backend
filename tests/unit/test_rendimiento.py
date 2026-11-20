"""Caso 9 con dobles: cierres, cobertura y acumulados; ninguna base real."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.adapters import mongo_adapter, influx_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.rendimiento import ControlTracking, IntervaloTracking
from app.services.rendimiento_service import (
    agregar_tracking, consolidar_jugadores, obtener_acumulados, obtener_rendimiento,
)
from scripts.consolidar_jugadores import registrar_control

INICIO = datetime(2030, 6, 24, 20, tzinfo=timezone.utc)
ARG = dict(codigo='ARG', nombre='Argentina')
ESP = dict(codigo='ESP', nombre='España')
URL = '/partidos/P-001/jugadores/ARG-10/estadisticas'


def evento(codigo, tipo='gol', autor='ARG-10', asistente=None):
    equipo = ARG if autor.startswith('ARG') else ESP
    protagonistas = [dict(jugador=dict(codigo=autor, nombre=autor), rol='autor')]
    if asistente:
        protagonistas.append(dict(jugador=dict(codigo=asistente, nombre=asistente), rol='asistente'))
    return dict(codigo=codigo, tipo=tipo, minuto=1, adicional=0, equipo=equipo, protagonistas=protagonistas)


@pytest.fixture
def datos(monkeypatch, cache_redis):
    jugadores = ('ARG-9', 'ARG-10', 'ESP-10')
    intervalo = dict(desde=INICIO.isoformat(), hasta=(INICIO + timedelta(seconds=2)).isoformat(), muestras=3)
    doc = dict(_id='P-001', fecha_hora=INICIO, fase='Grupos', grupo='A', sede=None,
        local=ARG, visitante=ESP, estado='en_vivo', actualizado_en=INICIO,
        resultado=dict(goles_local=2, goles_visitante=0, penales=None),
        reloj=dict(periodo='segundo_tiempo', minuto=90, adicional=0),
        eventos=[evento('g1', asistente='ARG-9'), evento('g2'),
                 evento('ta', 'tarjeta_amarilla', 'ESP-10')],
        tracking_control=dict(revision='tracking-1', completa=True,
                              jugadores={j: [deepcopy(intervalo)] for j in jugadores}))
    docs, resumenes, tracking = {'P-001': doc}, {}, {}
    for j in jugadores:
        tracking[j] = [dict(time=(INICIO + timedelta(seconds=n)).isoformat(), jugador_id=j,
            equipo_id=j.split('-')[0], distancia_acum_m=100 + n * 4, velocidad_kmh=10 + n) for n in range(3)]
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', lambda c: deepcopy(docs.get(c)))
    monkeypatch.setattr(mongo_adapter, 'list_partidos_jugador', lambda _: deepcopy(list(docs.values())))
    def jugador(c):
        if c == 'ARG-99':
            return None
        equipo = ARG if c.startswith('ARG') else ESP
        return dict(_id=c, nombre=c, apellido='', equipo=dict(_id=equipo['codigo'], nombre=equipo['nombre']))
    monkeypatch.setattr(mongo_adapter, 'find_jugador', jugador)
    monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', Mock(side_effect=lambda p, j, *_: deepcopy(tracking[j])))
    monkeypatch.setattr(mongo_adapter, 'find_resumen_jugador', Mock(side_effect=lambda p, g, j: deepcopy(resumenes.get(f'{p}:{g}:{j}'))))
    def publicar(c, anterior, manifiesto, filas):
        for fila in filas:
            resumenes[fila['_id']] = deepcopy(fila)
        if anterior != docs[c]:
            return False
        docs[c]['jugadores_finales'] = deepcopy(manifiesto)
        return True
    monkeypatch.setattr(mongo_adapter, 'publicar_resumenes_jugadores', Mock(side_effect=publicar))
    monkeypatch.setattr(mongo_adapter, 'guardar_control_tracking', Mock(return_value=True))
    return docs, resumenes, tracking


def test_vivo_deportivas_fisicas_y_cache(client, datos, cache_redis):
    r = client.get(URL)
    assert r.status_code == 200, r.text
    assert r.json()['metricas'] == dict(goles=2, asistencias=0, tarjetas_amarillas=0,
        tarjetas_rojas=0, distancia_m=8., velocidad_max_kmh=12.)
    assert r.json()['consolidacion'] == 'provisional'
    influx_adapter.find_tracking_jugador.reset_mock()
    assert client.get(URL).json() == r.json()
    influx_adapter.find_tracking_jugador.assert_not_called()
    assert obtener_rendimiento('P-001', 'ARG-9').metricas.asistencias == 1
    assert obtener_rendimiento('P-001', 'ESP-10').metricas.tarjetas_amarillas == 1


def test_cierre_repetido_final_sin_influx_ni_redis(client, datos, monkeypatch):
    docs, _, _ = datos
    docs['P-001']['estado'] = 'finalizado'
    consolidar_jugadores('P-001')
    primero = obtener_acumulados('ARG-10')
    consolidar_jugadores('P-001')
    segundo = obtener_acumulados('ARG-10')
    assert primero.metricas == segundo.metricas
    assert segundo.metricas.goles == 2 and segundo.partidos_consolidados == 1
    assert segundo.metricas.distancia_m == 8 and segundo.metricas.velocidad_max_kmh == 12
    monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', Mock(side_effect=AssertionError('No leer Influx')))
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get(URL).json()['consolidacion'] == 'completa'
    assert client.get('/jugadores/ARG-10/estadisticas').json()['metricas']['goles'] == 2


def test_correccion_invalida_y_reemplaza_sin_doble_conteo(datos):
    docs, _, _ = datos
    d = docs['P-001']
    d['estado'] = 'finalizado'
    consolidar_jugadores('P-001')
    d['eventos'][1] = evento('g2', autor='ARG-9')
    pendiente = obtener_rendimiento('P-001', 'ARG-10')
    assert pendiente.consolidacion == 'pendiente' and pendiente.metricas.goles == 1
    assert pendiente.metricas.distancia_m is None
    consolidar_jugadores('P-001')
    assert obtener_acumulados('ARG-10').metricas.goles == 1
    assert obtener_acumulados('ARG-9').metricas.goles == 1


def test_acumulado_mezcla_eventos_y_resumenes_sin_influx(datos, monkeypatch):
    docs, _, _ = datos
    d = docs['P-001']
    d['estado'] = 'finalizado'
    consolidar_jugadores('P-001')
    docs['P-002'] = {**deepcopy(d), '_id': 'P-002', 'estado': 'en_vivo'}
    monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', Mock(side_effect=AssertionError('No leer Influx')))
    r = obtener_acumulados('ARG-10')
    assert r.metricas.goles == 4 and r.metricas.distancia_m is None
    assert r.partidos_consolidados == 1 and r.partidos_pendientes == 1
    assert r.consolidacion == 'provisional'


@pytest.mark.parametrize('fallo', ['caida', 'hueco', 'duplicado', 'reset', 'nan', 'otro_jugador'])
def test_tracking_incompleto_no_inventa_ceros_y_no_publica(datos, monkeypatch, fallo):
    docs, _, tracking = datos
    if fallo == 'caida':
        monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', Mock(side_effect=DatabaseUnavailableError('InfluxDB')))
    elif fallo == 'hueco':
        tracking['ARG-10'].pop(1)
    elif fallo == 'duplicado':
        tracking['ARG-10'][1] = deepcopy(tracking['ARG-10'][0])
    elif fallo == 'reset':
        tracking['ARG-10'][1]['distancia_acum_m'] = 0
    elif fallo == 'nan':
        tracking['ARG-10'][1]['velocidad_kmh'] = float('nan')
    else:
        tracking['ARG-10'][1]['jugador_id'] = 'ESP-10'
    r = obtener_rendimiento('P-001', 'ARG-10')
    assert r.metricas.goles == 2 and r.metricas.distancia_m is None
    assert r.consolidacion == 'pendiente'
    docs['P-001']['estado'] = 'finalizado'
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')
    mongo_adapter.publicar_resumenes_jugadores.assert_not_called()


def test_autogol_no_suma_gol_ni_asistencia_y_tanda_separada(datos):
    docs, _, _ = datos
    d = docs['P-001']
    d['eventos'][1] = evento('g2', 'autogol', autor='ESP-10')
    d['resultado']['penales'] = dict(goles_local=5, goles_visitante=3)
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.goles == 1
    assert obtener_rendimiento('P-001', 'ESP-10').metricas.goles == 0


def test_evento_duplicado_o_marcador_inconsistente_no_consolida(datos):
    docs, _, _ = datos
    d = docs['P-001']
    d['eventos'].append(deepcopy(d['eventos'][0]))
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.goles is None
    d['estado'] = 'finalizado'
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')


def test_publicacion_fallida_no_expone_generacion_incompleta(datos, monkeypatch):
    docs, resumenes, _ = datos
    d = docs['P-001']
    d['estado'] = 'finalizado'
    consolidar_jugadores('P-001')
    generacion = deepcopy(d['jugadores_finales'])
    def parcial(c, anterior, manifiesto, filas):
        resumenes[filas[0]['_id']] = filas[0]
        return False
    monkeypatch.setattr(mongo_adapter, 'publicar_resumenes_jugadores', parcial)
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')
    assert d['jugadores_finales'] == generacion
    assert obtener_rendimiento('P-001', 'ARG-10').consolidacion == 'completa'


def test_faltante_resumen_final_no_se_cuenta_completo(datos, monkeypatch):
    docs, resumenes, _ = datos
    docs['P-001']['estado'] = 'finalizado'
    consolidar_jugadores('P-001')
    resumenes.clear()
    monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', Mock(side_effect=AssertionError('No leer Influx')))
    r = obtener_acumulados('ARG-10')
    assert r.partidos_consolidados == 0 and r.metricas.goles == 2
    assert r.metricas.distancia_m is None and r.consolidacion == 'pendiente'


def test_control_debe_estar_cerrado_y_cubrir_participantes(datos):
    docs, _, _ = datos
    d = docs['P-001']
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')
    d['estado'] = 'finalizado'
    d['tracking_control']['completa'] = False
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')
    d['tracking_control']['completa'] = True
    d['tracking_control']['jugadores'].pop('ARG-9')
    with pytest.raises(ValueError):
        consolidar_jugadores('P-001')


def test_intervalos_y_base_no_cero(datos):
    _, _, tracking = datos
    i = IntervaloTracking(desde=INICIO, hasta=INICIO + timedelta(seconds=2), muestras=3)
    assert agregar_tracking(tracking['ARG-10'], i, 'ARG-10', 'ARG') == (8, 12)
    with pytest.raises(ValueError):
        IntervaloTracking(desde=INICIO, hasta=INICIO + timedelta(seconds=2), muestras=2)
    with pytest.raises(ValueError):
        ControlTracking(revision='r1', completa=True, jugadores={'ARG-10': [i, i]})


def test_proximo_sin_datos_no_consulta_influx(client, datos):
    docs, _, _ = datos
    d = docs['P-001']
    # La convocatoria real conserva el vínculo; aquí el control no cuenta sin reloj.
    d.update(estado='proximo', resultado=None, reloj=None)
    r = client.get(URL)
    assert r.status_code == 404  # Los eventos previos no demuestran convocatoria futura.
    influx_adapter.find_tracking_jugador.assert_not_called()


@pytest.mark.parametrize('url,esperado', [
    ('/partidos/P-001/jugadores/arg-10/estadisticas', 400),
    ('/partidos/xxx/jugadores/ARG-10/estadisticas', 400),
    ('/jugadores/ARG-0/estadisticas', 400),
    ('/partidos/P-001/jugadores/ARG-99/estadisticas', 404),
    ('/partidos/P-999/jugadores/ARG-10/estadisticas', 404),
    ('/partidos/P-001/jugadores/ARG-20/estadisticas', 404),
])
def test_validacion_y_ausentes(client, datos, url, esperado):
    assert client.get(url).status_code == esperado


def test_mongo_caido_devuelve_error_seguro(client, datos, monkeypatch):
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', Mock(side_effect=DatabaseUnavailableError('MongoDB')))
    assert client.get(URL).status_code == 503


def test_registro_control_protege_reemplazo_y_valida_referencias(datos):
    docs, _, _ = datos
    control = ControlTracking.model_validate(docs['P-001']['tracking_control'])
    registrar_control('P-001', control)
    mongo_adapter.guardar_control_tracking.assert_not_called()
    control.revision = 'tracking-2'
    with pytest.raises(ValueError):
        registrar_control('P-001', control)
    registrar_control('P-001', control, reemplazar=True)
    mongo_adapter.guardar_control_tracking.assert_called_once()


def test_varios_intervalos_no_suman_bases_y_velocidad_es_maximo(datos, monkeypatch):
    docs, _, tracking = datos
    d = docs['P-001']
    segundo = dict(desde=(INICIO + timedelta(seconds=10)).isoformat(),
        hasta=(INICIO + timedelta(seconds=11)).isoformat(), muestras=2)
    d['tracking_control']['jugadores']['ARG-10'].append(segundo)
    filas = deepcopy(tracking['ARG-10']) + [dict(time=(INICIO + timedelta(seconds=n)).isoformat(),
        jugador_id='ARG-10', equipo_id='ARG', distancia_acum_m=500 + (n - 10) * 5,
        velocidad_kmh=20) for n in (10, 11)]
    monkeypatch.setattr(influx_adapter, 'find_tracking_jugador', lambda p, j, e, desde, hasta: [
        f for f in filas if datetime.fromisoformat(desde) <= datetime.fromisoformat(f['time']) <= datetime.fromisoformat(hasta)])
    r = obtener_rendimiento('P-001', 'ARG-10')
    assert r.metricas.distancia_m == 13 and r.metricas.velocidad_max_kmh == 20


def test_suplente_sin_ingreso_puede_confirmar_cero_pero_titular_no(datos):
    docs, _, _ = datos
    d = docs['P-001']
    def jugador(n):
        return dict(codigo=f'ARG-{n}', nombre=f'Jugador {n}', dorsal=n, posicion='Delantero')
    d['alineaciones'] = dict(local=dict(equipo=ARG, titulares=[jugador(n) for n in range(1, 12)],
        suplentes=[jugador(12)]), visitante=None)
    d['tracking_control']['jugadores']['ARG-12'] = []
    r = obtener_rendimiento('P-001', 'ARG-12')
    assert r.metricas.goles == r.metricas.distancia_m == r.metricas.velocidad_max_kmh == 0
    d['tracking_control']['jugadores']['ARG-10'] = []
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.distancia_m is None


def test_proximo_convocado_y_acumulado_vacio(client, datos):
    docs, _, _ = datos
    d = docs['P-001']
    d.update(estado='proximo', resultado=None, reloj=None)
    d['alineaciones'] = dict(local=dict(equipo=ARG, titulares=[dict(codigo=f'ARG-{n}',
        nombre=f'Jugador {n}', dorsal=n, posicion='Delantero') for n in range(1, 12)], suplentes=[]))
    data = client.get(URL).json()
    assert data['consolidacion'] == 'sin_datos' and all(v is None for v in data['metricas'].values())
    acumulado = obtener_acumulados('ARG-10')
    assert acumulado.consolidacion == 'sin_datos' and acumulado.partidos == []
    influx_adapter.find_tracking_jugador.assert_not_called()


def test_tracking_anclado_en_inicio_tracking(datos):
    docs, _, tracking = datos
    d = docs['P-001']
    real = datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)
    intervalo = dict(desde=real.isoformat(), hasta=(real + timedelta(seconds=2)).isoformat(), muestras=3)
    for jugador, filas in tracking.items():
        d['tracking_control']['jugadores'][jugador] = [dict(intervalo)]
        for n, fila in enumerate(filas):
            fila['time'] = (real + timedelta(seconds=n)).isoformat()
    # Sin inicio_tracking el intervalo queda fuera de fecha_hora + reloj.
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.distancia_m is None
    d['inicio_tracking'] = real
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.distancia_m == 8.
    # Con inicio_tracking, el tracking precargado en el horario del calendario ya no es válido.
    d['tracking_control']['jugadores']['ARG-10'] = [dict(desde=INICIO.isoformat(),
        hasta=(INICIO + timedelta(seconds=2)).isoformat(), muestras=3)]
    assert obtener_rendimiento('P-001', 'ARG-10').metricas.distancia_m is None
