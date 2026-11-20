"""Caso 8 con adaptadores en memoria: no escribe bases de desarrollo."""
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from app.adapters import mongo_adapter, redis_adapter, influx_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.services.comparacion_service import agregar_muestras, consolidar, obtener_comparacion
from scripts.simular_estadisticas import PlanEstadisticas, ejecutar
from scripts.simular_partido import crear_plan


@pytest.fixture
def escenario(monkeypatch):
    doc = dict(_id='P-002', fase='Grupos', grupo='A', fecha_hora=datetime(2030, 6, 24, 20),
        local=dict(codigo='ARG', nombre='Argentina'), visitante=dict(codigo='ESP', nombre='España'),
        estado='proximo', resultado=None, sede=None)
    monkeypatch.setattr(mongo_adapter, 'find_eventos', lambda _: deepcopy(doc))
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', lambda _: deepcopy(doc))
    monkeypatch.setattr(mongo_adapter, 'find_jugador', lambda c: dict(_id=c, nombre='Jugador',
        apellido=c.split('-')[1], equipo={'_id': c.split('-')[0]}))
    monkeypatch.setattr(mongo_adapter, 'list_jugadores', lambda c, *_: [dict(_id=f'{c}-{d}',
        nombre='Jugador', apellido=str(d), dorsal=d, posicion='Delantero') for d in (9, 10)])
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', lambda _: {})
    def guardar(_, anterior, cambios):
        if anterior != doc:
            return False
        doc.update(deepcopy(cambios))
        return True
    monkeypatch.setattr(mongo_adapter, 'guardar_seguimiento', Mock(side_effect=guardar))
    monkeypatch.setattr(mongo_adapter, 'guardar_estadisticas', Mock(side_effect=guardar))
    monkeypatch.setattr(type(mongo_adapter), 'db', property(lambda _: Mock()))
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(return_value=None))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock())
    monkeypatch.setattr(redis_adapter, 'delete_cache', Mock())
    monkeypatch.setattr(redis_adapter, 'delete_cache_matching', Mock())
    monkeypatch.setattr(mongo_adapter, 'list_cruces', lambda: [])
    deportivo = crear_plan('P-002')
    plan = PlanEstadisticas(inicio='2030-06-24T20:00:00Z', local=doc['local'], visitante=doc['visitante'], deportivo=deportivo)
    filas = {}
    def escribir(lineas):
        for linea in lineas.splitlines():
            tags, campos, ts = linea.split(' ')
            equipo = tags.split('equipo_id=')[1]
            values = {k: float(v.rstrip('i')) for k, v in (p.split('=') for p in campos.split(','))}
            filas[(int(ts), equipo)] = dict(time=datetime.fromtimestamp(int(ts), timezone.utc).isoformat(), equipo_id=equipo, **values)
    monkeypatch.setattr(influx_adapter, 'escribir_muestras', Mock(side_effect=escribir))
    monkeypatch.setattr(influx_adapter, 'find_muestras', Mock(side_effect=lambda *_: list(filas.values())))
    return doc, plan, filas


def test_seed_cierre_y_reintento_sin_duplicados(client, escenario, monkeypatch):
    doc, plan, filas = escenario
    ejecutar(plan, 0)
    final = client.get('/partidos/P-002/estadisticas')
    assert final.status_code == 200
    data = final.json()
    assert data['consolidacion'] == 'completa'
    assert (data['local']['goles'], data['visitante']['goles']) == (2, 0)
    assert (data['local']['tiros'], data['visitante']['tiros']) == (14, 7)
    assert (data['local']['pases'], data['visitante']['pases']) == (360, 270)
    assert data['visitante']['tarjetas_amarillas'] == data['visitante']['tarjetas_rojas'] == 1
    assert data['local']['posesion_pct'] + data['visitante']['posesion_pct'] == 100
    assert len(filas) == 2162 and len(doc['eventos']) == 5
    ejecutar(plan, 0)
    assert len(filas) == 2162 and len(doc['eventos']) == 5
    assert mongo_adapter.guardar_seguimiento.call_count == 9
    # Finales con Influx y caché caídos: no consulta ninguna de las dos fuentes.
    monkeypatch.setattr(influx_adapter, 'find_muestras', Mock(side_effect=AssertionError('No leer Influx')))
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert obtener_comparacion('P-002').local.pases == 360
    # Una corrección invalida el resumen aunque no cambie actualizado_en.
    doc['eventos'][1]['tipo'] = 'tarjeta_roja'
    assert obtener_comparacion('P-002').consolidacion == 'pendiente'
    assert obtener_comparacion('P-002').local.pases is None


def test_recupera_fallo_despues_de_tick_confirmado(escenario, monkeypatch):
    doc, plan, filas = escenario
    real = mongo_adapter.guardar_estadisticas.side_effect
    fallar = True
    def guardar(codigo, anterior, cambios):
        nonlocal fallar
        if fallar and cambios.get('estadisticas_control', {}).get('tick') == 2:
            fallar = False
            return False
        return real(codigo, anterior, cambios)
    monkeypatch.setattr(mongo_adapter, 'guardar_estadisticas', Mock(side_effect=guardar))
    with pytest.raises(ValueError):
        ejecutar(plan, 0)
    assert doc['reloj']['minuto'] == 28 and doc['estadisticas_control']['tick'] == 1
    ejecutar(plan, 0)
    assert doc['estado'] == 'finalizado' and len(doc['eventos']) == 5 and len(filas) == 2162
    assert obtener_comparacion('P-002').consolidacion == 'completa'


def test_cierre_incompleto_no_publica_resumen(escenario):
    doc, plan, filas = escenario
    ejecutar(plan, 0)
    doc.pop('estadisticas_finales')
    filas.pop(next(iter(filas)))
    with pytest.raises(ValueError):
        consolidar('P-002')
    assert 'estadisticas_finales' not in doc
    assert obtener_comparacion('P-002').consolidacion == 'pendiente'


def test_proximo_vacio_y_errores_de_query(client, escenario, monkeypatch):
    data = client.get('/partidos/P-002/estadisticas').json()
    assert data['consolidacion'] == 'sin_datos' and data['local']['goles'] is None
    influx_adapter.find_muestras.assert_not_called()
    mongo_adapter.guardar_estadisticas.assert_not_called()
    for query in ('?desde=2030-06-24T20:00:00Z', '?hasta=2030-06-24T20:00:00Z', '?ventana=1m', '?equipo=ARG'):
        assert client.get('/partidos/P-002/estadisticas' + query).status_code == 400
    monkeypatch.setattr(mongo_adapter, 'find_estadisticas', Mock(return_value=None))
    assert client.get('/partidos/P-999/estadisticas').status_code == 404


def test_vivo_degradado_conserva_deportivas_y_no_inventa_ceros(escenario, monkeypatch):
    doc, plan, _ = escenario
    doc.update(estado='en_vivo', reloj=plan.deportivo.ticks[0].reloj.model_dump(), eventos=[],
        resultado=dict(goles_local=0, goles_visitante=0, penales=None), estadisticas_control=plan.control(0))
    monkeypatch.setattr(influx_adapter, 'find_muestras', Mock(side_effect=DatabaseUnavailableError('InfluxDB')))
    data = obtener_comparacion('P-002')
    assert data.local.goles == 0 and data.local.pases is None
    assert data.consolidacion == 'pendiente' and data.advertencias
    # Caché rota también permite devolver deportivas.
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert obtener_comparacion('P-002').local.goles == 0


def test_autogol_y_tanda_no_se_cuentan_dos_veces(escenario):
    doc, plan, _ = escenario
    e = plan.deportivo.ticks[1].eventos[0].model_dump()
    e['tipo'] = 'autogol'
    doc.update(estado='finalizado', eventos=[e], resultado=dict(goles_local=0, goles_visitante=1,
        penales=dict(goles_local=5, goles_visitante=4)))
    data = obtener_comparacion('P-002')
    assert data.local.goles == 0 and data.visitante.goles == 1


def test_promedio_ponderado_contadores_y_huecos():
    filas = []
    for e in ('ARG', 'ESP'):
        for segundo, d, p, t, pa in ((0, 0, 50, 0, 0), (5, 5, 80, 2, 3), (20, 15, 40, 3, 5)):
            filas.append(dict(time=f'2030-06-24T20:00:{segundo:02d}Z', equipo_id=e, duracion_s=d,
                posesion_pct=p if e == 'ARG' else 100 - p, tiros_acumulados=t, pases_intervalo=pa))
    control = dict(inicio=filas[0]['time'], hasta=filas[-1]['time'], muestras=6)
    result = agregar_muestras(filas, control, ['ARG', 'ESP'])
    assert result['ARG'] == dict(posesion_pct=50, tiros=3, pases=8)
    for field, value in [('duracion_s', 5), ('tiros_acumulados', 1), ('posesion_pct', float('nan')), ('pases_intervalo', -1)]:
        invalidas = deepcopy(filas)
        invalidas[2][field] = value
        with pytest.raises(ValueError):
            agregar_muestras(invalidas, control, ['ARG', 'ESP'])


def test_rechaza_otro_plan_y_partido_finalizado_ajeno(escenario):
    doc, plan, _ = escenario
    doc['estado'] = 'finalizado'
    with pytest.raises(ValueError):
        ejecutar(plan, 0)
    influx_adapter.escribir_muestras.assert_not_called()
    doc.update(estado='proximo', estadisticas_control={**plan.control(-1), 'plan': 'a' * 64})
    with pytest.raises(ValueError):
        ejecutar(plan, 0)
    influx_adapter.escribir_muestras.assert_not_called()


def test_no_sobrescribe_muestras_preexistentes(escenario):
    _, plan, filas = escenario
    filas['otra-carga'] = plan.muestras(0, 0)[0]
    with pytest.raises(ValueError):
        ejecutar(plan, 0)
    mongo_adapter.guardar_estadisticas.assert_not_called()
    influx_adapter.escribir_muestras.assert_not_called()


def test_vivo_completo_cache_versionada_y_reloj_desfasado(escenario, monkeypatch):
    doc, plan, filas = escenario
    for tick in plan.deportivo.ticks[:2]:
        from app.services.seguimiento_service import aplicar_tick
        aplicar_tick('P-002', tick)
    doc['estadisticas_control'] = plan.control(1)
    for f in plan.muestras(0, 720):
        filas[(f['time'], f['equipo_id'])] = f
    data = obtener_comparacion('P-002')
    assert data.consolidacion == 'provisional' and data.local.goles == 1
    assert data.local.tiros == 1 and data.local.pases == 48
    key = redis_adapter.set_cache.call_args.args[0]
    assert redis_adapter.set_cache.call_args.args[2] == 5
    # Nueva tarjeta y reloj cambian la versión, aunque Influx aún no haya confirmado.
    doc['reloj']['minuto'] = 28
    data = obtener_comparacion('P-002')
    assert data.consolidacion == 'pendiente' and data.local.pases is None
    assert redis_adapter.get_cache.call_args.args[0] != key


def test_correccion_reprocesable_y_conflicto_de_consolidacion(escenario, monkeypatch):
    doc, plan, _ = escenario
    ejecutar(plan, 0)
    doc['eventos'][1]['tipo'] = 'tarjeta_roja'
    assert obtener_comparacion('P-002').consolidacion == 'pendiente'
    resumen = consolidar('P-002')
    assert resumen.visitante.tarjetas_rojas == 2 and resumen.visitante.tarjetas_amarillas == 0
    assert obtener_comparacion('P-002').consolidacion == 'completa'
    monkeypatch.setattr(mongo_adapter, 'guardar_estadisticas', Mock(return_value=False))
    with pytest.raises(ValueError, match='cambió'):
        consolidar('P-002')


def test_valida_todas_las_referencias_antes_de_escribir(escenario, monkeypatch):
    _, plan, _ = escenario
    plan.deportivo.ticks[6].eventos[0].protagonistas[0].jugador.nombre = 'Nombre obsoleto'
    with pytest.raises(ValueError):
        ejecutar(plan, 0)
    mongo_adapter.guardar_estadisticas.assert_not_called()
    influx_adapter.escribir_muestras.assert_not_called()


def test_adapter_escritura_atomica_parametros_y_fallo(monkeypatch):
    from app.adapters.influx_adapter import InfluxAdapter
    import requests
    adapter = InfluxAdapter()
    session = Mock()
    monkeypatch.setattr(adapter, 'get_session', lambda: session)
    monkeypatch.setattr(adapter, '_resolve_token', lambda: 'token-prueba')
    adapter.escribir_muestras('estadisticas_partido,partido_id=P-002,equipo_id=ARG posesion_pct=55.0 1908561600\n')
    kwargs = session.post.call_args.kwargs
    assert kwargs['params']['precision'] == 'second'
    assert kwargs['params']['accept_partial'] == 'false' and kwargs['params']['no_sync'] == 'false'
    assert isinstance(kwargs['data'], bytes)
    session.post.side_effect = requests.Timeout()
    with pytest.raises(DatabaseUnavailableError):
        adapter.escribir_muestras('linea')


def test_adapter_tabla_ausente_y_columna_heredada(monkeypatch):
    from app.adapters.influx_adapter import InfluxAdapter
    adapter = InfluxAdapter()
    query = Mock(return_value=[])
    monkeypatch.setattr(adapter, 'query_sql', query)
    assert adapter.find_muestras('P-002', 'inicio', 'fin') == []
    assert query.call_count == 1
    query.side_effect = [[{'table_name': 'estadisticas_partido'}], [{'column_name': 'posesion_pct'}], []]
    assert adapter.find_muestras('P-002', 'inicio', 'fin') == []
    sql, params = query.call_args.args
    assert 'NULL AS duracion_s' in sql and 'LIMIT 10001' in sql
    assert params == dict(partido='P-002', desde='inicio', hasta='fin')


def test_preparacion_influx_repetible_preserva_config_y_no_expone_token(tmp_path, monkeypatch, capsys):
    import json
    from scripts import preparar_influx_local as preparar
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(preparar, 'ROOT', tmp_path)
    monkeypatch.delenv('INFLUX_DATABASE', raising=False)
    monkeypatch.delenv('INFLUX_ESTADISTICAS_PORT', raising=False)
    env = tmp_path / '.env'
    original = 'API_PORT=8000\nMONGO_URI=mongodb://127.0.0.1:27018\nINFLUX_TOKEN=anterior\n'
    env.write_text(original)
    def run(args, **kwargs):
        return Mock(stdout='fixture2030-estadisticas\n' if args[1] == 'inspect' else json.dumps({'token': 'secreto-prueba'}))
    monkeypatch.setattr(preparar.subprocess, 'run', run)
    monkeypatch.setattr(preparar.requests, 'post', Mock(return_value=Mock(status_code=200)))
    preparar.main()
    assert preparar.dotenv_values(env)['MONGO_URI'] == 'mongodb://127.0.0.1:27018'
    assert preparar.dotenv_values(env)['INFLUX_TOKEN'] == 'secreto-prueba'
    assert (tmp_path / '.env.antes-estadisticas').read_text() == original
    assert env.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(preparar.requests, 'post', Mock(return_value=Mock(status_code=400)))
    monkeypatch.setattr(preparar.requests, 'get', Mock(return_value=Mock(json=lambda: [{'iox::database': 'fixture2030_resumen'}])))
    preparar.main()
    assert (tmp_path / '.env.antes-estadisticas').read_text() == original
    assert 'secreto-prueba' not in capsys.readouterr().out


def test_vivo_lee_las_muestras_desde_inicio_tracking(escenario):
    doc, plan, filas = escenario
    from app.services.seguimiento_service import aplicar_tick
    for tick in plan.deportivo.ticks[:2]:
        aplicar_tick('P-002', tick)
    inicio_tracking = datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)
    doc['inicio_tracking'] = inicio_tracking
    # Las precargadas en el horario del partido quedan fuera de la lectura.
    for f in plan.muestras(0, 720) + plan.muestras(0, 720, inicio_tracking):
        filas[(f['time'], f['equipo_id'])] = f
    influx_adapter.find_muestras.side_effect = lambda _, desde, hasta: [
        f for f in filas.values() if desde <= f['time'].replace('+00:00', 'Z') <= hasta]
    doc['estadisticas_control'] = plan.control(1, inicio_tracking)
    data = obtener_comparacion('P-002')
    assert data.consolidacion == 'provisional' and data.local.pases == 48
    assert influx_adapter.find_muestras.call_args.args[1:] == ('2026-11-20T18:30:00Z', '2026-11-20T18:42:00Z')
    # Un control anclado en el horario no corresponde a un partido simulado en vivo.
    doc['estadisticas_control'] = plan.control(1)
    assert obtener_comparacion('P-002').consolidacion == 'pendiente'


def test_inicio_temporal_prefiere_inicio_tracking_redondeado():
    from app.services.comparacion_service import inicio_temporal
    assert inicio_temporal('2030-06-24T20:00:00Z') == datetime(2030, 6, 24, 20, tzinfo=timezone.utc)
    assert inicio_temporal(datetime(2030, 6, 24, 20), datetime(2026, 11, 20, 18, 30, 42)) == \
        datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)
