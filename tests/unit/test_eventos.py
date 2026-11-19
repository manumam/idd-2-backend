"""Cronología e ingesta con almacenamiento en memoria; no escriben bases reales."""
from copy import deepcopy
from datetime import datetime
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.adapters import mongo_adapter, redis_adapter, neo4j_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.partidos import EventoResponse
from app.services.seguimiento_service import TickPartido, aplicar_tick
from scripts.simular_partido import PlanPartido, crear_plan, jugadores_de_campo, participantes_demo
from app.schemas.alineaciones import AlineacionEquipo

LOCAL = dict(codigo='ARG', nombre='Argentina')
VISITA = dict(codigo='ESP', nombre='España')


def evento(codigo='gol-1', tipo='gol', minuto=12, equipo=None, adicional=0):
    equipo = equipo or LOCAL
    roles = ['sale', 'entra'] if tipo == 'cambio' else ['autor']
    return dict(codigo=codigo, tipo=tipo, minuto=minuto, adicional=adicional, equipo=equipo,
        protagonistas=[dict(jugador=dict(codigo=f'{equipo["codigo"]}-{i+1}', nombre=f'Jugador {i+1}'), rol=rol)
                       for i, rol in enumerate(roles)])


def tick(minuto, eventos=(), finalizado=False, adicional=0):
    return TickPartido(reloj=dict(periodo='primer_tiempo' if minuto <= 45 else 'segundo_tiempo',
                                  minuto=minuto, adicional=adicional), eventos=list(eventos), finalizado=finalizado)


@pytest.fixture
def almacen(monkeypatch):
    doc = dict(_id='P-001', fecha_hora=datetime(2030, 6, 24, 20), fase='Grupos', grupo='A',
               local=LOCAL, visitante=VISITA, sede=None, estado='proximo', resultado=None)
    monkeypatch.setattr(mongo_adapter, 'find_eventos', lambda codigo: deepcopy(doc) if codigo == 'P-001' else None)
    monkeypatch.setattr(mongo_adapter, 'find_partido', lambda codigo: {k: deepcopy(v) for k, v in doc.items() if k != 'eventos'})
    def jugador(codigo):
        eq, dorsal = codigo.split('-')
        return dict(_id=codigo, nombre='Jugador', apellido=dorsal, equipo={'_id': eq})
    monkeypatch.setattr(mongo_adapter, 'find_jugador', jugador)
    def guardar(codigo, anterior, cambios):
        assert anterior == doc
        doc.update(deepcopy(cambios))
        return True
    monkeypatch.setattr(mongo_adapter, 'guardar_seguimiento', Mock(side_effect=guardar))
    cache = {}
    monkeypatch.setattr(redis_adapter, 'get_cache', lambda key: cache.get(key))
    monkeypatch.setattr(redis_adapter, 'set_cache', lambda key, value, ttl: cache.update({key: value}))
    monkeypatch.setattr(redis_adapter, 'delete_cache', Mock())
    monkeypatch.setattr(neo4j_adapter, 'find_eventos', Mock(side_effect=AssertionError('No usar Neo4j')))
    return doc, cache


def test_recorrido_completo_y_cierre(client, almacen):
    doc, _ = almacen
    assert client.get('/partidos/P-001/eventos').json()['items'] == []
    assert aplicar_tick('P-001', tick(0))
    gol = evento()
    aplicar_tick('P-001', tick(12, [gol]))
    aplicar_tick('P-001', tick(28, [evento('amarilla', 'tarjeta_amarilla', 28, VISITA)]))
    aplicar_tick('P-001', tick(62, [evento('cambio', 'cambio', 62)]))
    aplicar_tick('P-001', tick(90, [evento('roja', 'tarjeta_roja', 90, VISITA, 2)], adicional=2))
    aplicar_tick('P-001', tick(90, finalizado=True, adicional=2))
    respuesta = client.get('/partidos/P-001/eventos').json()
    assert respuesta['total'] == 4 and respuesta['estado'] == 'finalizado'
    assert respuesta['resultado']['goles_local'] == 1
    assert respuesta['reloj']['adicional'] == 2
    assert respuesta['items'][2]['protagonistas'][1]['rol'] == 'entra'
    assert client.get('/partidos/P-001').json()['resultado'] == respuesta['resultado']
    assert doc['estado'] == 'finalizado'
    assert redis_adapter.delete_cache.call_count == 6


def test_generador_y_reproduccion_del_guion_sin_motores(client, almacen, monkeypatch):
    doc, cache = almacen
    def plantel(equipo, *_):
        return [dict(_id=f'{equipo}-{i}', nombre='Jugador', apellido=str(i), dorsal=i,
                     posicion='Arquero' if i == 1 else 'Delantero') for i in (1, 2, 9)]
    monkeypatch.setattr(mongo_adapter, 'list_jugadores', plantel)
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', lambda _: {'_id': 'P-001'})
    plan = crear_plan('P-001')
    assert len(plan.ticks) == 9 and doc['estado'] == 'proximo' and cache == {}
    mongo_adapter.guardar_seguimiento.assert_not_called()
    goles = [e for paso in plan.ticks for e in paso.eventos if e.tipo == 'gol']
    cambio = next(e for paso in plan.ticks for e in paso.eventos if e.tipo == 'cambio')
    assert [e.protagonistas[0].jugador.codigo for e in goles] == ['ARG-9', 'ARG-2']
    assert [(p.rol, p.jugador.codigo) for p in cambio.protagonistas] == [('sale', 'ARG-9'), ('entra', 'ARG-2')]
    for paso in plan.ticks:
        aplicar_tick(plan.partido, paso)
    data = client.get('/partidos/P-001/eventos').json()
    assert data['estado'] == 'finalizado' and data['total'] == 5
    assert data['resultado']['goles_local'] == 2 and data['resultado']['goles_visitante'] == 0


def test_generador_prioriza_posicion_y_dorsal_sin_elegir_arqueros():
    plantel = [dict(_id=f'ARG-{d}', dorsal=d, posicion=p) for d, p in
               [(99, 'Arquero'), (26, 'Defensor'), (20, 'Delantero'), (9, 'Delantero'), (24, 'Mediocampista')]]
    assert [j['_id'] for j in jugadores_de_campo(plantel)] == ['ARG-20', 'ARG-9', 'ARG-24', 'ARG-26']
    with pytest.raises(ValueError, match='jugadores de campo'):
        participantes_demo(plantel[:1], None, True)


def test_generador_respeta_titulares_y_suplentes():
    jugadores = [dict(codigo=f'ARG-{i}', nombre=f'Jugador {i}', dorsal=i,
                     posicion='Arquero' if i in (1, 12) else 'Delantero') for i in range(1, 15)]
    alineacion = AlineacionEquipo(equipo=LOCAL, titulares=jugadores[:11], suplentes=jugadores[11:])
    plantel = [dict(_id=j['codigo'], dorsal=j['dorsal'], posicion=j['posicion']) for j in jugadores]
    seleccion = participantes_demo(plantel, alineacion, True)
    assert [j['_id'] for j in seleccion] == ['ARG-11', 'ARG-14']
    alineacion.suplentes = alineacion.suplentes[:1]  # Solo queda un arquero en el banco.
    with pytest.raises(ValueError, match='suplente de campo'):
        participantes_demo(plantel, alineacion, True)


def test_reenvio_y_autogol(client, almacen):
    gol = evento()
    aplicar_tick('P-001', tick(12, [gol]))
    aplicar_tick('P-001', tick(12, [gol]))
    aplicar_tick('P-001', tick(45, [evento('auto', 'autogol', 45)]))
    data = client.get('/partidos/P-001/eventos').json()
    assert data['total'] == 2
    assert data['resultado'] == dict(goles_local=1, goles_visitante=1, penales=None)


def test_paginacion_orden_y_claves_versionadas(client, almacen):
    doc, cache = almacen
    aplicar_tick('P-001', tick(46, [evento('b', minuto=45, adicional=2), evento('a', minuto=45)]))
    primera = client.get('/partidos/P-001/eventos?limit=1').json()
    segunda = client.get('/partidos/P-001/eventos?limit=1&skip=1').json()
    assert primera['items'][0]['codigo'] == 'a' and primera['siguiente_skip'] == 1
    assert segunda['items'][0]['codigo'] == 'b' and segunda['siguiente_skip'] is None
    assert primera['total'] == 2
    antes = set(cache)
    aplicar_tick('P-001', tick(62, [evento('c', minuto=62)]))
    data = client.get('/partidos/P-001/eventos?limit=1').json()
    assert data['total'] == 3 and data['resultado']['goles_local'] == 3
    assert set(cache) != antes
    assert client.get('/partidos/P-001/eventos?skip=99').json()['items'] == []


@pytest.mark.parametrize('query', ['limit=0', 'limit=201', 'skip=-1', 'skip=abc'])
def test_parametros_invalidos(client, monkeypatch, query):
    lectura = Mock(side_effect=AssertionError('No consultar'))
    monkeypatch.setattr(mongo_adapter, 'find_eventos', lectura)
    assert client.get('/partidos/P-001/eventos?' + query).status_code == 400
    lectura.assert_not_called()


def test_no_encontrado_y_sin_redis(client, almacen, monkeypatch):
    assert client.get('/partidos/P-999/eventos').status_code == 404
    for metodo in ('get_cache', 'set_cache'):
        monkeypatch.setattr(redis_adapter, metodo, Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/partidos/P-001/eventos').status_code == 200


def test_rechaza_referencias_y_no_escribe(almacen, monkeypatch):
    for invalido in [evento(equipo=dict(codigo='URU', nombre='Uruguay')),
                     evento(minuto=90), evento(equipo=dict(codigo='ARG', nombre='Otro'))]:
        with pytest.raises(ValueError):
            aplicar_tick('P-001', tick(12, [invalido]))
    monkeypatch.setattr(mongo_adapter, 'find_jugador', lambda _: None)
    with pytest.raises(ValueError):
        aplicar_tick('P-001', tick(12, [evento()]))
    mongo_adapter.guardar_seguimiento.assert_not_called()


def test_conflicto_y_no_reabrir_final(almacen, monkeypatch):
    doc, _ = almacen
    monkeypatch.setattr(mongo_adapter, 'guardar_seguimiento', Mock(return_value=False))
    with pytest.raises(ValueError, match='cambió'):
        aplicar_tick('P-001', tick(12, [evento()]))
    doc.update(estado='finalizado', resultado=dict(goles_local=1, goles_visitante=0),
               reloj=tick(90).reloj.model_dump(), eventos=[evento()])
    assert aplicar_tick('P-001', tick(90, finalizado=True)) is False
    with pytest.raises(ValueError, match='finalizado'):
        aplicar_tick('P-001', tick(90, [evento('nuevo', minuto=90)], finalizado=True))


def test_roles_y_minutos_y_plan():
    for cambios in [dict(tipo='otro'), dict(minuto=-1), dict(minuto=True), dict(adicional=-1),
                    dict(protagonistas=[]), dict(tipo='cambio')]:
        with pytest.raises(ValidationError):
            EventoResponse.model_validate({**evento(), **cambios})
    with pytest.raises(ValidationError):
        PlanPartido(partido='P-001', ticks=[tick(12, [evento()]), tick(28, [evento()])])
    with pytest.raises(ValidationError):
        PlanPartido(partido='P-001', ticks=[tick(90, finalizado=True), tick(91)])


def test_persistencia_invalida_y_cache_corrupta(client, almacen, monkeypatch):
    doc, _ = almacen
    aplicar_tick('P-001', tick(12, [evento()]))
    monkeypatch.setattr(redis_adapter, 'get_cache', lambda _: '{broken')
    assert client.get('/partidos/P-001/eventos').status_code == 200
    doc['eventos'][0]['tipo'] = 'desconocido'
    response = client.get('/partidos/P-001/eventos')
    assert response.status_code == 500 and response.json()['code'] == 'EVENTOS_INVALIDOS'
