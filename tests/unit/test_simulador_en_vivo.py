"""Simulación en vivo con reloj y adaptadores en memoria: no duerme ni escribe bases."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import requests

from app.adapters import mongo_adapter, redis_adapter
from app.adapters.influx_adapter import INTENTOS_POR_LOTE, InfluxAdapter
from app.config.settings import settings
from app.services.seguimiento_service import TickPartido
from scripts import cargar_influx
from scripts.simular_en_vivo import (
    DURACION_SEG, EscritorInflux, MetricasSimulador, GeneradorMuestras, bases_configuradas, RelojSimulado, confederaciones_del_torneo, inicio_tracking_desde,
    simular, ticks_vencidos, titulares_de_archivos)
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
    assert tablas['estadisticas_partido'] == line_protocol(plan, plan.muestras(0, 5400, INICIO_TRACKING)).splitlines()
    assert len(tablas['estadisticas_partido']) == 2162


def test_anclas_de_tiempo_y_series_de_cada_tabla(plan):
    generador = GeneradorMuestras(plan, titulares_de_archivos([DEMO_P001], plan), ['UEFA'], INICIO_TRACKING)
    tablas = generador.lineas(0, 5)
    inicio = int(INICIO_TRACKING.timestamp())
    assert tablas['tracking_jugador'][0].startswith('tracking_jugador,partido_id=P-001,equipo_id=URU,jugador_id=URU-1 ')
    assert tablas['tracking_jugador'][-1].endswith(f' {inicio + 5}')
    assert [l.rsplit(' ', 1)[1] for l in tablas['tracking_pelota']] == [str(inicio + s) for s in range(6)]
    assert [l.rsplit(' ', 1)[1] for l in tablas['actividad_usuarios']] == [str(inicio), str(inicio + 5)]
    # También las del caso 8: las de la carga masiva quedan en el horario del partido, sin choque.
    assert [l.rsplit(' ', 1)[1] for l in tablas['estadisticas_partido']] == [str(inicio)] * 2 + [str(inicio + 5)] * 2
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


EN_VIVO, RESUMEN = settings.influx_database_en_vivo, settings.influx_database
BASES = {'tracking_jugador': EN_VIVO, 'tracking_pelota': EN_VIVO,
         'estadisticas_partido': RESUMEN, 'actividad_usuarios': RESUMEN}


def _respuesta(status):
    respuesta = requests.Response()
    respuesta.status_code = status
    return respuesta


def _adaptador(session, token=None):
    adaptador = InfluxAdapter()
    adaptador.get_session = lambda: session
    adaptador._resolve_token = lambda: token
    return adaptador


def test_escritor_un_lote_por_tabla_en_su_base(plan):
    session = MagicMock()
    session.post.return_value = _respuesta(204)
    escritor = EscritorInflux(_adaptador(session, 'secreto'), BASES)
    lineas = GeneradorMuestras(plan, titulares_de_archivos([DEMO_P001], plan), ['UEFA'], INICIO_TRACKING).lineas(0, 9)
    assert escritor.escribir(lineas) == 0
    destinos = [(c.kwargs['params']['db'], c.kwargs['data'].decode().split(',', 1)[0]) for c in session.post.call_args_list]
    assert destinos == [(EN_VIVO, 'tracking_jugador'), (EN_VIVO, 'tracking_pelota'),
                        (RESUMEN, 'estadisticas_partido'), (RESUMEN, 'actividad_usuarios')]
    assert all(c.kwargs['params']['precision'] == 'second' for c in session.post.call_args_list)
    assert escritor.contadores['tracking_jugador'] == dict(base=EN_VIVO, escritas=220, rechazadas=0)
    assert escritor.contadores['estadisticas_partido']['escritas'] == 4
    assert escritor.contadores['actividad_usuarios']['escritas'] == 2


def test_escritor_reintenta_y_cuenta_rechazos_por_tabla():
    session = MagicMock()
    session.post.side_effect = [_respuesta(500), _respuesta(204), *[_respuesta(503)] * INTENTOS_POR_LOTE]
    escritor = EscritorInflux(_adaptador(session), BASES)
    rechazadas = escritor.escribir({'tracking_pelota': ['a 1', 'b 1'], 'tracking_jugador': [],
                                    'actividad_usuarios': ['c 1']})
    assert rechazadas == 1
    assert session.post.call_count == 2 + INTENTOS_POR_LOTE
    assert escritor.contadores['tracking_pelota'] == dict(base=EN_VIVO, escritas=2, rechazadas=0)
    assert escritor.contadores['actividad_usuarios'] == dict(base=RESUMEN, escritas=0, rechazadas=1)
    assert escritor.contadores['tracking_jugador'] == dict(base=EN_VIVO, escritas=0, rechazadas=0)


def test_bases_por_defecto_son_las_que_leen_los_casos():
    bases = bases_configuradas()
    assert bases['tracking_jugador'] == bases['tracking_pelota'] == settings.influx_database_en_vivo
    assert bases['estadisticas_partido'] == bases['actividad_usuarios'] == settings.influx_database


class RelojFalso:
    """Avanza solo cuando el simulador duerme: el recorrido completo no espera tiempo real."""

    def __init__(self):
        self.ahora = 0.0
        self.esperas = 0

    def __call__(self):
        return self.ahora

    def dormir(self, segundos):
        assert segundos > 0
        self.esperas += 1
        self.ahora += segundos


class InfluxFalso:
    def __init__(self, rechazar=False):
        self.rechazar = rechazar
        self.lineas = {}
        self.estadisticas = {}

    def post(self, url, params, data, headers, timeout):
        if self.rechazar:
            return _respuesta(500)
        for linea in data.decode().splitlines():
            tags, campos, ts = linea.split(' ')
            tabla = tags.split(',', 1)[0]
            self.lineas.setdefault(tabla, []).append(linea)
            if tabla == 'estadisticas_partido':
                equipo = tags.split('equipo_id=')[1]
                valores = {k: float(v.rstrip('i')) for k, v in (p.split('=') for p in campos.split(','))}
                self.estadisticas[(int(ts), equipo)] = dict(
                    time=datetime.fromtimestamp(int(ts), timezone.utc).isoformat(), equipo_id=equipo, **valores)
        return _respuesta(204)

    def muestras(self, _partido, desde, hasta):
        from app.services.comparacion_service import instante
        return [f for (ts, _), f in sorted(self.estadisticas.items())
                if instante(desde).timestamp() <= ts <= instante(hasta).timestamp()]


@pytest.fixture
def en_vivo(monkeypatch, plan, cache_redis):
    from app.adapters import influx_adapter
    doc = partido_proximo('P-001', plan.local.model_dump(), plan.visitante.model_dump())
    monkeypatch.setattr(mongo_adapter, 'find_eventos', lambda _: deepcopy(doc))
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', lambda _: deepcopy(doc))
    monkeypatch.setattr(mongo_adapter, 'find_jugador', lambda c: dict(_id=c, nombre='Jugador',
        apellido=c.split('-')[1], equipo={'_id': c.split('-')[0]}))
    monkeypatch.setattr(mongo_adapter, 'list_cruces', lambda: [])
    monkeypatch.setattr(type(mongo_adapter), 'db', property(lambda _: MagicMock()))
    influx = InfluxFalso()
    confirmados = []

    def guardar(_, anterior, cambios):
        if anterior != doc:
            return False
        if 'reloj' in cambios:
            # Cada tick deportivo se confirma con sus estadísticas ya escritas.
            ultimo = max((ts for ts, _ in influx.estadisticas), default=None)
            confirmados.append((cambios['reloj']['minuto'], ultimo))
        doc.update(deepcopy(cambios))
        return True
    monkeypatch.setattr(mongo_adapter, 'guardar_seguimiento', MagicMock(side_effect=guardar))
    monkeypatch.setattr(mongo_adapter, 'guardar_estadisticas', MagicMock(side_effect=guardar))
    monkeypatch.setattr(influx_adapter, 'find_muestras', MagicMock(side_effect=influx.muestras))
    return doc, influx, confirmados


def _ocupacion_falsa(codigo, _influx):
    return dict(partido=codigo, enviadas=0, rechazadas=0)


def _simular(plan, influx, factor=10, informar=None, materializar=_ocupacion_falsa):
    reloj = RelojFalso()
    escritor = EscritorInflux(_adaptador(influx), BASES)
    resultado = simular(plan, factor, titulares_de_archivos([DEMO_P001], plan), ['CONMEBOL', 'UEFA'], escritor,
                        reloj=reloj, dormir=reloj.dormir, ahora=datetime(2026, 11, 20, 18, 30, 42, tzinfo=timezone.utc),
                        informar=informar or (lambda _: None), materializar=materializar)
    return resultado, reloj


def test_recorrido_completo_avanza_mongo_e_influx_al_mismo_ritmo(plan, en_vivo, cache_redis):
    import json
    doc, influx, confirmados = en_vivo
    avisos = []
    resultado, reloj = _simular(plan, influx, informar=avisos.append)
    assert doc['estado'] == 'finalizado' and doc['reloj']['minuto'] == 90
    assert doc['resultado']['goles_local'] == 2 and len(doc['eventos']) == 5
    assert doc['inicio_tracking'] == INICIO_TRACKING
    assert doc['estadisticas_control']['completa'] and resultado['consolidacion'] == 'completa'
    assert doc['estadisticas_finales']['resumen']['local']['pases'] == 360
    # 90 minutos en 9 reales, un lote por segundo real.
    assert 540 <= reloj.ahora < 541 and 530 <= reloj.esperas <= 541
    assert resultado['tablas']['tracking_jugador']['escritas'] == 22 * 5400
    assert resultado['tablas']['tracking_pelota']['escritas'] == 5400
    assert resultado['tablas']['estadisticas_partido']['escritas'] == 2162
    assert resultado['tablas']['actividad_usuarios']['escritas'] == 1080 * 2
    assert all(t['rechazadas'] == 0 for t in resultado['tablas'].values())
    inicio = int(INICIO_TRACKING.timestamp())
    tiempos = sorted({int(l.rsplit(' ', 1)[1]) for l in influx.lineas['tracking_jugador']})
    assert tiempos == list(range(inicio, inicio + 5400))
    assert doc['estadisticas_control']['inicio'] == '2026-11-20T18:30:00Z'
    for minuto, ultimo in confirmados:
        assert ultimo >= inicio + minuto * 60
    ticks = [json.loads(a) for a in avisos]
    assert [t['minuto'] for t in ticks] == [0, 12, 28, 45, 46, 62, 78, 82, 90]
    assert all(t['minuto'] * 60 <= t['segundo_de_juego'] < t['minuto'] * 60 + 10 for t in ticks)
    invalidaciones = [c.args[0] for c in redis_adapter.delete_cache_matching.call_args_list]
    assert invalidaciones.count('mapa_calor:v2:P-001:*') == 9


def test_factor_alto_aplica_todos_los_ticks_en_orden(plan, en_vivo):
    doc, influx, confirmados = en_vivo
    resultado, reloj = _simular(plan, influx, factor=2000)
    assert [m for m, _ in confirmados] == [0, 12, 28, 45, 46, 62, 78, 82, 90]
    assert doc['estado'] == 'finalizado' and reloj.ahora < 4
    assert resultado['tablas']['tracking_pelota']['escritas'] == 5400


def test_rechazo_de_influx_detiene_antes_de_confirmar_el_tick(plan, en_vivo):
    doc, _, confirmados = en_vivo
    with pytest.raises(ValueError, match='rechazó'):
        _simular(plan, InfluxFalso(rechazar=True))
    assert confirmados == [] and doc['estado'] == 'proximo'
    assert doc['inicio_tracking'] == INICIO_TRACKING and doc['estadisticas_control']['tick'] == -1
    # Una ejecución cortada no se reanuda: hay que restaurar el partido o elegir otro.
    with pytest.raises(ValueError, match='restaurarlo'):
        _simular(plan, InfluxFalso())


def test_no_simula_partidos_iniciados_ni_con_muestras_en_su_inicio_real(plan, en_vivo):
    doc, influx, _ = en_vivo
    doc['estado'] = 'en_vivo'
    doc['resultado'] = dict(goles_local=0, goles_visitante=0, penales=None)
    with pytest.raises(ValueError, match='próximo'):
        _simular(plan, influx)
    assert 'inicio_tracking' not in doc
    doc.update(estado='proximo', resultado=None)
    inicio = int(INICIO_TRACKING.timestamp())
    influx.estadisticas[(inicio + 60, 'URU')] = dict(time='2026-11-20T18:31:00+00:00', equipo_id='URU')
    with pytest.raises(ValueError, match='muestras'):
        _simular(plan, influx)
    assert 'inicio_tracking' not in doc


def test_muestras_precargadas_en_el_horario_no_impiden_simular(plan, en_vivo):
    doc, influx, _ = en_vivo
    precargadas = plan.muestras(0, 5400)
    for fila in precargadas:
        influx.estadisticas[(int(datetime.fromisoformat(fila['time']).timestamp()), fila['equipo_id'])] = fila
    resultado, _ = _simular(plan, influx)
    assert doc['estado'] == 'finalizado' and resultado['consolidacion'] == 'completa'
    assert len(influx.estadisticas) == 2 * len(precargadas)


def test_solo_validar_no_conecta(plan, tmp_path, monkeypatch, capsys):
    import json
    import sys
    from scripts import simular_en_vivo
    archivo = tmp_path / 'plan.json'
    archivo.write_text(plan.model_dump_json())
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', MagicMock(side_effect=AssertionError('No conectar')))
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', MagicMock(side_effect=AssertionError('No conectar')))
    monkeypatch.setattr(sys, 'argv', ['simular_en_vivo.py', str(archivo), '--solo-validar', '--factor', '20'])
    simular_en_vivo.main()
    salida = json.loads(capsys.readouterr().out)
    assert salida['duracion_real_s'] == 270 and salida['jugadores_con_tracking'] == 22
    assert salida['ticks'][1] == dict(minuto=12, segundo_real=36)
    assert salida['puntos']['tracking_jugador'] == 22 * 5400 and salida['puntos']['estadisticas_partido'] == 2162
    assert salida['bases_modificadas'] is False


def test_factor_invalido_y_alineaciones_solo_al_validar(plan, tmp_path, monkeypatch):
    import sys
    from scripts import simular_en_vivo
    archivo = tmp_path / 'plan.json'
    archivo.write_text(plan.model_dump_json())
    for argumentos in (['--factor', '0'], ['--alineaciones', str(DEMO_P001)]):
        monkeypatch.setattr(sys, 'argv', ['simular_en_vivo.py', str(archivo), *argumentos])
        with pytest.raises(SystemExit):
            simular_en_vivo.main()


def _metrica(escritor, nombre, **etiquetas):
    return escritor.metricas.registro.get_sample_value(nombre, etiquetas)


def test_metricas_de_ticks_puntos_segundo_y_retraso(plan, en_vivo):
    _, influx, _ = en_vivo
    reloj = RelojFalso()
    escritor = EscritorInflux(_adaptador(influx), BASES)
    simular(plan, 10, titulares_de_archivos([DEMO_P001], plan), ['UEFA'], escritor, reloj=reloj, dormir=reloj.dormir,
            ahora=INICIO_TRACKING, informar=lambda _: None, materializar=_ocupacion_falsa)
    assert _metrica(escritor, 'simulador_ticks_aplicados_total') == 9
    assert _metrica(escritor, 'simulador_puntos_escritos_total', tabla='tracking_jugador') == 22 * 5400
    assert _metrica(escritor, 'simulador_puntos_escritos_total', tabla='estadisticas_partido') == 2162
    assert _metrica(escritor, 'simulador_puntos_rechazados_total', tabla='tracking_pelota') == 0
    assert _metrica(escritor, 'simulador_segundo_de_juego') == DURACION_SEG
    # El reloj falso no avanza mientras escribe: no hay retraso.
    assert _metrica(escritor, 'simulador_retraso_segundos') == 0
    nombres = {m.name for m in escritor.metricas.registro.collect()}
    assert not any(n.startswith('api_') for n in nombres)
    etiquetas = {k for m in escritor.metricas.registro.collect() for muestra in m.samples for k in muestra.labels}
    assert etiquetas <= {'tabla'}


def test_metricas_cuentan_rechazos_por_tabla():
    session = MagicMock()
    session.post.return_value = _respuesta(400)
    escritor = EscritorInflux(_adaptador(session), BASES)
    escritor.escribir({'tracking_pelota': ['a 1', 'b 1']})
    assert _metrica(escritor, 'simulador_puntos_rechazados_total', tabla='tracking_pelota') == 2
    assert _metrica(escritor, 'simulador_puntos_escritos_total', tabla='tracking_pelota') == 0


def test_metricas_se_exponen_en_todas_las_interfaces_con_su_registro(monkeypatch):
    from scripts import simular_en_vivo
    servidor = MagicMock()
    monkeypatch.setattr(simular_en_vivo, 'start_http_server', servidor)
    metricas = MetricasSimulador(BASES)
    metricas.exponer(9105)
    servidor.assert_called_once_with(9105, addr='0.0.0.0', registry=metricas.registro)


class OcupacionFalsa:
    """Tracking leído al finalizar: registra cuándo se materializa respecto del estado del partido."""

    def __init__(self, doc, rechazadas=0, falla=None):
        self.doc, self.rechazadas, self.falla = doc, rechazadas, falla
        self.lotes, self.estado_al_leer = [], None

    def query_sql(self, query, params=None, database=None):
        if self.falla:
            raise self.falla
        self.estado_al_leer = self.doc['estado']
        assert database == settings.influx_database_en_vivo and params['partido'] == 'P-001'
        return [{'jugador_id': 'URU-1', 'equipo_id': 'URU', 'minuto': '2026-11-20T18:30:00',
                 'columna': 3.0, 'fila': 2.0, 'muestras': 60}]

    def escribir_lineas(self, base, lineas):
        self.lotes.append((base, list(lineas)))
        return self.rechazadas


class RedisScriptsFalso:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def scan_iter(self, match, count):
        return []


def _materializar_con(ocupacion):
    from scripts.simular_en_vivo import materializar_al_finalizar
    return lambda codigo, _influx: materializar_al_finalizar(codigo, ocupacion, RedisScriptsFalso)


def test_al_finalizar_materializa_la_ocupacion_y_la_informa(plan, en_vivo):
    doc, influx, _ = en_vivo
    ocupacion = OcupacionFalsa(doc)
    resultado, _ = _simular(plan, influx, materializar=_materializar_con(ocupacion))
    assert ocupacion.estado_al_leer == 'finalizado'
    assert resultado['ocupacion'] == dict(partido='P-001', enviadas=1, rechazadas=0)
    base, lineas = ocupacion.lotes[0]
    assert base == settings.influx_database and lineas[0].startswith('ocupacion_jugador_minuto,partido_id=P-001,')
    assert resultado['consolidacion'] == 'completa'


@pytest.mark.parametrize('falla, rechazadas, esperado', [
    (RuntimeError('caído'), 0, dict(partido='P-001', error='RuntimeError')),
    (None, 1, dict(partido='P-001', enviadas=1, rechazadas=1)),
])
def test_falla_al_materializar_no_deshace_el_partido(plan, en_vivo, falla, rechazadas, esperado):
    doc, influx, _ = en_vivo
    resultado, _ = _simular(plan, influx, materializar=_materializar_con(OcupacionFalsa(doc, rechazadas, falla)))
    assert doc['estado'] == 'finalizado' and resultado['consolidacion'] == 'completa'
    assert resultado['ocupacion'] == dict(esperado,
        reintentar='.venv/bin/python scripts/materializar_ocupacion.py --partido P-001')


def test_sin_titulares_no_materializa(plan, en_vivo):
    _, influx, _ = en_vivo
    reloj = RelojFalso()
    materializar = MagicMock()
    resultado = simular(plan, 2000, [], ['UEFA'], EscritorInflux(_adaptador(influx), BASES), reloj=reloj,
                        dormir=reloj.dormir, ahora=INICIO_TRACKING, informar=lambda _: None, materializar=materializar)
    materializar.assert_not_called()
    assert resultado['ocupacion'] == dict(partido='P-001', enviadas=0, rechazadas=0)
