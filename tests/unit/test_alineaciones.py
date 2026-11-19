"""Convocatorias HTTP, cambios de plaza y carga sin motores reales."""
from copy import deepcopy
from unittest.mock import Mock, MagicMock
import pytest
from pydantic import ValidationError
from app.adapters import mongo_adapter, redis_adapter
from app.adapters.mongo_adapter import MongoAdapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.alineaciones import AlineacionEquipo
from scripts.cargar_alineaciones import Lote, preparar, cargar


def equipo(codigo='ARG'):
    return dict(equipo=dict(codigo=codigo, nombre=codigo), titulares=[dict(
        codigo=f'{codigo}-{n}', nombre=f'Jugador {n}', dorsal=n, posicion='Mediocampista'
    ) for n in range(1, 12)], suplentes=[dict(codigo=f'{codigo}-12', nombre='Suplente', dorsal=12, posicion='Arquero')])


@pytest.fixture
def fuentes(monkeypatch):
    doc = dict(_id='P-001', alineaciones=dict(local=equipo(), visitante=equipo('ESP')))
    detalle = dict(_id='P-001', fase='Grupos', grupo='A', fecha_hora='2030-06-09T12:00:00Z',
                   local=doc['alineaciones']['local']['equipo'], visitante=doc['alineaciones']['visitante']['equipo'],
                   estado='proximo', resultado=None)
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(return_value=detalle))
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', Mock(return_value=doc))
    cache = {}
    monkeypatch.setattr(redis_adapter, 'get_cache', lambda key: cache.get(key))
    monkeypatch.setattr(redis_adapter, 'set_cache', lambda key, value, ttl: cache.update({key: value}))
    return doc, detalle, cache


def test_http_convocatorias_correcciones_y_cache(client, fuentes):
    doc, _, cache = fuentes
    url = '/partidos/P-001/alineaciones'
    data = client.get(url).json()
    assert data['partido'] == 'P-001'
    assert len(data['local']['titulares']) == 11
    assert data['visitante']['suplentes'][0]['codigo'] == 'ESP-12'
    assert client.get(url).json() == data
    doc['alineaciones']['local']['titulares'][0]['posicion'] = 'Defensor'
    assert client.get(url).json()['local']['titulares'][0]['posicion'] == 'Defensor'
    assert len([k for k in cache if k.startswith('alineaciones:')]) == 2


def test_pendientes_y_plaza_obsoleta(client, fuentes):
    doc, detalle, _ = fuentes
    doc.pop('alineaciones')
    assert client.get('/partidos/P-001/alineaciones').json() == dict(partido='P-001', local=None, visitante=None)
    doc['alineaciones'] = dict(local=equipo(), visitante=None)
    detalle['local'] = dict(codigo='URU', nombre='Uruguay')
    assert client.get('/partidos/P-001/alineaciones').json()['local'] is None


def test_fallos_y_codigo(client, fuentes, monkeypatch):
    assert client.get('/partidos/INVALID/alineaciones').status_code == 400
    mongo_adapter.find_alineaciones.assert_not_called()
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(return_value=None))
    assert client.get('/partidos/P-001/alineaciones').status_code == 404
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(side_effect=DatabaseUnavailableError('MongoDB')))
    assert client.get('/partidos/P-001/alineaciones').status_code == 503


def test_redis_opcional_cache_corrupta_y_datos_invalidos(client, fuentes, monkeypatch):
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(return_value='{}'))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/partidos/P-001/alineaciones').status_code == 200
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/partidos/P-001/alineaciones').status_code == 200
    fuentes[0]['alineaciones']['local']['titulares'].pop()
    response = client.get('/partidos/P-001/alineaciones')
    assert response.status_code == 500 and response.json()['code'] == 'ALINEACIONES_INVALIDAS'


@pytest.mark.parametrize('error', ['repetido', 'dorsal', 'seleccion', 'titulares', 'dorsal_bool'])
def test_validacion(error):
    a = equipo()
    if error == 'repetido': a['suplentes'][0] = deepcopy(a['titulares'][0])
    if error == 'dorsal': a['suplentes'][0]['dorsal'] = 1
    if error == 'seleccion': a['suplentes'][0]['codigo'] = 'ESP-12'
    if error == 'titulares': a['titulares'].pop()
    if error == 'dorsal_bool': a['titulares'][0]['dorsal'] = True
    with pytest.raises(ValidationError): AlineacionEquipo.model_validate(a)


def test_proyeccion_acotada():
    adapter = MongoAdapter()
    adapter._db, adapter._client = MagicMock(), Mock()
    adapter.find_alineaciones('P-001')
    assert adapter._db.__getitem__.return_value.find_one.call_args.args == (
        {'_id': 'P-001'}, {'_id': 1, 'alineaciones': 1})


def test_carga_referencias_y_conservacion():
    lote = Lote.model_validate(dict(partidos=[dict(partido='P-001', alineaciones=dict(local=equipo()))]))
    partidos = [dict(_id='P-001', local=equipo()['equipo'])]
    jugadores = [dict(_id=f'ARG-{i}', equipo={'_id': 'ARG'}) for i in range(1, 13)]
    docs = preparar(lote, partidos, jugadores)
    db = Mock()
    db.partidos.update_one.return_value.modified_count = 1
    assert cargar(db, docs)['actualizados'] == 1
    filtro, update = db.partidos.update_one.call_args.args
    assert filtro == {'_id': 'P-001', 'alineaciones': None}
    assert set(update['$set']) == {'alineaciones'}
    cargar(db, docs, reemplazar=True)
    assert db.partidos.update_one.call_args.args[0] == {'_id': 'P-001'}
    with pytest.raises(ValueError): preparar(lote, partidos, jugadores[:-1])
    with pytest.raises(ValueError): preparar(lote, [], jugadores)
    with pytest.raises(ValueError): preparar(lote, [dict(_id='P-001', local=None)], jugadores)
    with pytest.raises(ValidationError): Lote.model_validate(dict(partidos=[lote.partidos[0], lote.partidos[0]]))


@pytest.mark.parametrize('raw', [[], False, '', {'local': {}}])
def test_datos_corruptos_no_parecen_pendientes(client, fuentes, raw):
    fuentes[0]['alineaciones'] = raw
    assert client.get('/partidos/P-001/alineaciones').json()['code'] == 'ALINEACIONES_INVALIDAS'


def test_cache_no_oculta_borrado_o_timeout_de_alineaciones(client, fuentes, monkeypatch):
    from pymongo.errors import NetworkTimeout
    assert client.get('/partidos/P-001/alineaciones').status_code == 200
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', Mock(return_value=None))
    assert client.get('/partidos/P-001/alineaciones').status_code == 404
    monkeypatch.setattr(mongo_adapter, 'find_alineaciones', Mock(side_effect=DatabaseUnavailableError('MongoDB', NetworkTimeout('secreto'))))
    response = client.get('/partidos/P-001/alineaciones')
    assert response.status_code == 504 and 'secreto' not in response.text


def test_seed_argentina_coincide_con_fixture_y_catalogo():
    from pathlib import Path
    from scripts.cargar_jugadores import preparar as jugadores
    from scripts.cargar_inicio_mundial import preparar as inicio
    lote = Lote.model_validate_json(Path('data/fixture/alineaciones-argentina-demo.json').read_text())
    docs = preparar(lote, inicio()[1], jugadores())
    assert {p.partido for p in docs} == {'P-002', 'P-051', 'P-083'}
    for entrada in docs:
        a = entrada.alineaciones.local
        assert a.equipo.codigo == 'ARG' and entrada.alineaciones.visitante is None
        assert len(a.titulares) == 11 and len(a.suplentes) == 15
        assert 'ARG-10' in {j.codigo for j in a.titulares}
        assert {j.codigo for j in a.titulares + a.suplentes} == {f'ARG-{n}' for n in range(1, 27)}


def test_recarga_seed_conserva_alineaciones_existentes():
    db = Mock()
    db.partidos.update_one.return_value.modified_count = 0
    lote = Lote.model_validate(dict(partidos=[dict(partido='P-001', alineaciones=dict(local=equipo()))]))
    assert cargar(db, lote.partidos) == {'actualizados': 0, 'conservados': 1}
    assert db.partidos.update_one.call_args.args[0] == {'_id': 'P-001', 'alineaciones': None}


def formacion_valida():
    return dict(arquero='ARG-1', lineas=[['ARG-2', 'ARG-3', 'ARG-4', 'ARG-5'], ['ARG-6', 'ARG-7', 'ARG-8'], ['ARG-9', 'ARG-10', 'ARG-11']])


def test_formacion_http_correcciones_y_compatibilidad(client, fuentes):
    a = fuentes[0]['alineaciones']['local']
    assert client.get('/partidos/P-001/alineaciones').json()['local']['formacion'] is None
    a['formacion'] = formacion_valida()
    data = client.get('/partidos/P-001/alineaciones').json()
    assert data['local']['formacion'] == a['formacion']
    a['formacion']['lineas'][0].reverse()
    assert client.get('/partidos/P-001/alineaciones').json()['local']['formacion'] == a['formacion']


@pytest.mark.parametrize('error', ['repetido', 'suplente', 'faltante', 'fila_vacia', 'muchas_lineas', 'desconocido'])
def test_formacion_rechaza_disposiciones_invalidas(error):
    a = equipo()
    a['formacion'] = formacion_valida()
    f = a['formacion']
    if error == 'repetido': f['lineas'][0][0] = f['arquero']
    if error == 'suplente': f['lineas'][0][0] = 'ARG-12'
    if error == 'faltante': f['lineas'][0].pop()
    if error == 'fila_vacia': f['lineas'].append([])
    if error == 'muchas_lineas': f['lineas'] = [[f'ARG-{i}'] for i in range(2, 12)]
    if error == 'desconocido': f['lineas'][0][0] = 'OTRO'
    with pytest.raises(ValidationError): AlineacionEquipo.model_validate(a)
