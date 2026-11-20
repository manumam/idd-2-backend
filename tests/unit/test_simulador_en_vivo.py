"""Simulación en vivo con reloj y adaptadores en memoria: no duerme ni escribe bases."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.adapters import mongo_adapter
from app.services.seguimiento_service import TickPartido
from scripts import cargar_influx
from scripts.simular_en_vivo import (
    DURACION_SEG, EscritorInflux, GeneradorMuestras, bases_configuradas, RelojSimulado, confederaciones_del_torneo, inicio_tracking_desde,
    ticks_vencidos, titulares_de_archivos)
from scripts.simular_estadisticas import PlanEstadisticas, line_protocol
from scripts.simular_partido import crear_plan

DEMO_P001 = cargar_influx.DATA / 'alineaciones-p001-demo.json'
DEMO_ARG = cargar_influx.DATA / 'alineaciones-argentina-demo.json'
INICIO_TRACKING = datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)


def partido_proximo(codigo, local, visitante):
    return dict(_id=codigo, fase='Grupos', grupo='A', fecha_hora=datetime(2030, 6, 8, 20),
                local=local, visitante=visitante, estado='proximo', resultado=None, sede=None)


def crear_plan_demo(monkeypatch, doc):
    monkeypatch.setattr(mongo_adapter, 'find_eventos', lambda _: deepcopy(doc))
    monkeypatch.setattr(mongo_adapter, 'list_jugadores', lambda c, *_: [dict(_id=f'{c}-{d}',
        nombre='Jugador', apellido=str(d), dorsal=d, posicion='Delantero') for d in (9, 10)])
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', lambda _: {})
    return PlanEstadisticas(inicio='2030-06-08T20:00:00Z', local=doc['local'], visitante=doc['visitante'],
                            deportivo=crear_plan(doc['_id']))


@pytest.fixture
def plan(monkeypatch):
    return crear_plan_demo(monkeypatch, partido_proximo(
        'P-001', dict(codigo='URU', nombre='Uruguay'), dict(codigo='KSA', nombre='Arabia Saudita')))


def _ticks(*minutos):
    return [TickPartido(reloj=dict(periodo='primer_tiempo', minuto=m)) for m in minutos]


def test_reloj_factor_diez_juega_noventa_minutos_en_nueve():
    reloj = RelojSimulado()
    assert reloj.segundo_en(0) == 0
    assert reloj.segundo_en(0.09) == 0
    assert reloj.segundo_en(1.25) == 12
    assert reloj.segundo_en(540) == 5400
    assert reloj.segundo_en(10_000) == 5400
    assert reloj.transcurrido_para(5400) == 540


def test_reloj_otro_factor_y_valores_invalidos():
    assert RelojSimulado(factor=1).segundo_en(61.9) == 61
    assert RelojSimulado(factor=0.5).transcurrido_para(30) == 60
    for factor in (0, -1, float('inf'), float('nan')):
        with pytest.raises(ValueError):
            RelojSimulado(factor)
    with pytest.raises(ValueError):
        RelojSimulado().segundo_en(-0.1)


def test_pendientes_no_repite_ni_saltea_segundos():
    reloj = RelojSimulado()
    assert list(reloj.pendientes(-1, 0)) == [0]
    assert list(reloj.pendientes(0, 0.35)) == [1, 2, 3]
    assert list(reloj.pendientes(3, 0.35)) == []
    assert list(reloj.pendientes(5398, 9999)) == [5399, 5400]


def test_ticks_del_guion_vencen_en_su_minuto():
    ticks = _ticks(0, 12, 28, 45, 46, 90)
    assert ticks_vencidos(ticks, 0, 0) == [0]
    assert ticks_vencidos(ticks, 1, 719) == []
    assert ticks_vencidos(ticks, 1, 720) == [1]
    # Un salto real largo dispara todos los ticks alcanzados, en orden.
    assert ticks_vencidos(ticks, 2, 2760) == [2, 3, 4]
    assert ticks_vencidos(ticks, 5, 5400) == [5]
    assert ticks_vencidos(ticks, 6, 5400) == []


def test_inicio_tracking_se_redondea_al_minuto_utc():
    ahora = datetime(2026, 11, 20, 15, 30, 42, 500, tzinfo=timezone(timedelta(hours=-3)))
    assert inicio_tracking_desde(ahora) == INICIO_TRACKING


def test_titulares_de_ambas_selecciones_o_solo_la_cargada(plan):
    titulares = titulares_de_archivos([DEMO_ARG, DEMO_P001], plan)
    assert len(titulares) == 22
    assert [e for _, e in titulares] == ['URU'] * 11 + ['KSA'] * 11
    plan.deportivo.partido = 'P-099'
    assert titulares_de_archivos([DEMO_P001], plan) == []


def test_rechaza_alineacion_de_otra_plaza(monkeypatch):
    otro = crear_plan_demo(monkeypatch, partido_proximo(
        'P-001', dict(codigo='KSA', nombre='Arabia Saudita'), dict(codigo='URU', nombre='Uruguay')))
    with pytest.raises(ValueError, match='local'):
        titulares_de_archivos([DEMO_P001], otro)


def _generar_por_tramos(generador, cortes):
    tablas = {}
    desde = 0
    for hasta in cortes:
        for tabla, lineas in generador.lineas(desde, hasta).items():
            tablas.setdefault(tabla, []).extend(lineas)
        desde = hasta + 1
    return tablas


def test_muestras_por_segundo_iguales_a_la_carga_masiva(plan):
    titulares = titulares_de_archivos([DEMO_P001], plan)
    regiones = confederaciones_del_torneo()
    generador = GeneradorMuestras(plan, titulares, regiones, INICIO_TRACKING)
    # Tramos irregulares, como los de un bucle real que se atrasa.
    tablas = _generar_por_tramos(generador, [0, 3, 4, 17, 1000, 5399, 5400])
    masivo = dict(codigo='P-001', inicio=int(INICIO_TRACKING.timestamp()), titulares=titulares)
    assert tablas['tracking_jugador'] == list(cargar_influx.lineas_tracking_jugador(masivo))
    assert tablas['tracking_pelota'] == list(cargar_influx.lineas_tracking_pelota(masivo))
    assert tablas['actividad_usuarios'] == list(cargar_influx.lineas_actividad_usuarios(masivo, regiones))
    assert len(tablas['tracking_jugador']) == 22 * DURACION_SEG
    # Estadísticas: exactamente las del caso 8, sin duplicar el muestreo de la carga masiva.
    assert tablas['estadisticas_partido'] == line_protocol(plan, plan.muestras(0, 5400)).splitlines()
    assert len(tablas['estadisticas_partido']) == 2162


def test_anclas_de_tiempo_y_series_de_cada_tabla(plan):
    generador = GeneradorMuestras(plan, titulares_de_archivos([DEMO_P001], plan), ['UEFA'], INICIO_TRACKING)
    tablas = generador.lineas(0, 5)
    inicio = int(INICIO_TRACKING.timestamp())
    assert tablas['tracking_jugador'][0].startswith('tracking_jugador,partido_id=P-001,equipo_id=URU,jugador_id=URU-1 ')
    assert tablas['tracking_jugador'][-1].endswith(f' {inicio + 5}')
    assert [l.rsplit(' ', 1)[1] for l in tablas['tracking_pelota']] == [str(inicio + s) for s in range(6)]
    assert [l.rsplit(' ', 1)[1] for l in tablas['actividad_usuarios']] == [str(inicio), str(inicio + 5)]
    plan_inicio = int(datetime(2030, 6, 8, 20, tzinfo=timezone.utc).timestamp())
    assert [l.rsplit(' ', 1)[1] for l in tablas['estadisticas_partido']] == [str(plan_inicio)] * 2 + [str(plan_inicio + 5)] * 2
    assert 'duracion_s=0i' in tablas['estadisticas_partido'][0]


def test_sin_alineaciones_solo_pelota_estadisticas_y_audiencia(plan):
    tablas = GeneradorMuestras(plan, [], ['UEFA'], INICIO_TRACKING).lineas(0, 9)
    assert tablas['tracking_jugador'] == []
    assert len(tablas['tracking_pelota']) == 10 and len(tablas['estadisticas_partido']) == 4


def test_segundos_en_orden_y_dentro_del_partido(plan):
    generador = GeneradorMuestras(plan, [], ['UEFA'], INICIO_TRACKING)
    with pytest.raises(ValueError):
        generador.lineas(1, 2)
    generador.lineas(0, 2)
    for desde, hasta in ((0, 3), (4, 5), (3, 2), (3, DURACION_SEG + 1)):
        with pytest.raises(ValueError):
            generador.lineas(desde, hasta)


BASES = {'tracking_jugador': 'en_vivo', 'tracking_pelota': 'en_vivo',
         'estadisticas_partido': 'resumen', 'actividad_usuarios': 'resumen'}


def _respuesta(status):
    return MagicMock(status_code=status)


def test_escritor_un_lote_por_tabla_en_su_base(plan):
    session = MagicMock()
    session.post.return_value = _respuesta(204)
    escritor = EscritorInflux(session, 'http://influx:8181', 'secreto', BASES)
    lineas = GeneradorMuestras(plan, titulares_de_archivos([DEMO_P001], plan), ['UEFA'], INICIO_TRACKING).lineas(0, 9)
    assert escritor.escribir(lineas) == 0
    destinos = [(c.kwargs['params']['db'], c.kwargs['data'].decode().split(',', 1)[0]) for c in session.post.call_args_list]
    assert destinos == [('en_vivo', 'tracking_jugador'), ('en_vivo', 'tracking_pelota'),
                        ('resumen', 'estadisticas_partido'), ('resumen', 'actividad_usuarios')]
    assert all(c.kwargs['params']['precision'] == 'second' for c in session.post.call_args_list)
    assert escritor.contadores['tracking_jugador'] == dict(base='en_vivo', escritas=220, rechazadas=0)
    assert escritor.contadores['estadisticas_partido']['escritas'] == 4
    assert escritor.contadores['actividad_usuarios']['escritas'] == 2


def test_escritor_reintenta_y_cuenta_rechazos_por_tabla():
    session = MagicMock()
    session.post.side_effect = [_respuesta(500), _respuesta(204),
                                *[_respuesta(503)] * cargar_influx.INTENTOS_POR_LOTE]
    escritor = EscritorInflux(session, 'http://influx:8181', None, BASES)
    rechazadas = escritor.escribir({'tracking_pelota': ['a 1', 'b 1'], 'tracking_jugador': [],
                                    'actividad_usuarios': ['c 1']})
    assert rechazadas == 1
    assert session.post.call_count == 2 + cargar_influx.INTENTOS_POR_LOTE
    assert escritor.contadores['tracking_pelota'] == dict(base='en_vivo', escritas=2, rechazadas=0)
    assert escritor.contadores['actividad_usuarios'] == dict(base='resumen', escritas=0, rechazadas=1)
    assert escritor.contadores['tracking_jugador'] == dict(base='en_vivo', escritas=0, rechazadas=0)


def test_bases_por_defecto_son_las_que_leen_los_casos():
    from app.config.settings import settings
    bases = bases_configuradas()
    assert bases['tracking_jugador'] == bases['tracking_pelota'] == settings.influx_database_en_vivo
    assert bases['estadisticas_partido'] == bases['actividad_usuarios'] == settings.influx_database
