from copy import deepcopy
from fnmatch import fnmatchcase
from unittest.mock import Mock, MagicMock, call
import pytest
from app.adapters import mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.grupos import Grupo
from app.schemas.fixture import PartidoFixture
from app.services.cache_partidos import borrar_cache_derivada, invalidar_resultado
from app.services.grupos_service import calcular_posiciones
from scripts.cargar_grupos import preparar
from scripts.cargar_inicio_mundial import preparar as inicio

G = dict(_id='A', equipos=[dict(codigo=c, nombre=c) for c in ('ARG', 'BRA', 'URU')],
         reglas=dict(victoria=3, empate=1, derrota=0, orden_desempate=['URU', 'BRA', 'ARG']))


def partido(code='P-001', local='ARG', visitante='BRA', estado='finalizado', goles=(2, 1)):
    return dict(_id=code, fecha_hora='2030-06-01T12:00:00Z', fase='Grupos', grupo='A',
                local=dict(codigo=local, nombre=local), visitante=dict(codigo=visitante, nombre=visitante),
                estado=estado, resultado=None if estado == 'proximo' else dict(goles_local=goles[0], goles_visitante=goles[1]))


def calcular(matches, group=G):
    return calcular_posiciones(Grupo(codigo=group['_id'], **{k:v for k,v in group.items() if k != '_id'}),
        [PartidoFixture(codigo=p['_id'], **{k:v for k,v in p.items() if k != '_id'}) for p in matches])


def test_tabla_finales_empate_derrota_no_cuenta_vivo_ni_penales():
    p = partido()
    p['resultado']['penales'] = dict(goles_local=8, goles_visitante=9)
    result = calcular([p, partido('P-002', 'BRA', 'URU', goles=(0, 0)), partido('P-003', 'ARG', 'URU', 'en_vivo', (4, 0))])
    assert not result.completa
    assert [(r.equipo.codigo, r.jugados, r.ganados, r.empatados, r.perdidos, r.puntos, r.goles_favor, r.goles_contra, r.diferencia_gol) for r in result.items] == [
        ('ARG', 1, 1, 0, 0, 3, 2, 1, 1), ('URU', 1, 0, 1, 0, 1, 0, 0, 0), ('BRA', 2, 0, 1, 1, 1, 1, 2, -1)]


def test_desempate_explicito_sin_partidos_y_grupo_completo():
    assert [r.equipo.codigo for r in calcular([]).items] == ['URU', 'BRA', 'ARG']
    result = calcular([partido(goles=(0,0)), partido('P-002', 'ARG', 'URU', goles=(0,0)), partido('P-003', 'BRA', 'URU', goles=(0,0))])
    assert result.completa and all(r.puntos == 2 for r in result.items)
    assert [r.equipo.codigo for r in result.items] == ['URU', 'BRA', 'ARG']


def test_orden_puntos_diferencia_y_goles():
    result = calcular([partido(goles=(3,0)), partido('P-002', 'BRA', 'URU', goles=(4,1)), partido('P-003', 'URU', 'ARG', goles=(2,1))])
    assert [r.equipo.codigo for r in result.items] == ['ARG', 'BRA', 'URU']
    result = calcular([partido(goles=(2,0)), partido('P-002', 'BRA', 'URU', goles=(3,1)), partido('P-003', 'URU', 'ARG', goles=(4,2))])
    assert [r.equipo.codigo for r in result.items] == ['URU', 'ARG', 'BRA']
    # Igual diferencia y goles a favor: resuelve el orden explícito del dataset.
    result = calcular([partido(goles=(2,0)), partido('P-002', 'BRA', 'URU', goles=(3,0)), partido('P-003', 'URU', 'ARG', goles=(2,1))])
    assert [r.equipo.codigo for r in result.items] == ['BRA', 'ARG', 'URU']


def test_rechaza_participantes_y_cruces_invalidos():
    for matches in ([partido(visitante='ESP')], [partido(), partido('P-002')]):
        with pytest.raises(ValueError): calcular(matches)
    invalid = deepcopy(G)
    invalid['reglas']['orden_desempate'] = ['ARG', 'ARG', 'BRA']
    with pytest.raises(ValueError): calcular([], invalid)


@pytest.fixture
def fuentes(monkeypatch, cache_redis):
    monkeypatch.setattr(mongo_adapter, 'list_grupos', Mock(return_value=[G]))
    monkeypatch.setattr(mongo_adapter, 'find_grupo', Mock(return_value=G))
    monkeypatch.setattr(mongo_adapter, 'list_cruces', Mock(return_value=[]))
    matches = Mock(return_value=[partido()])
    monkeypatch.setattr(mongo_adapter, 'list_partidos_grupo', matches)
    return matches, cache_redis


def test_http_correccion_cierre_e_invalidacion(client, fuentes):
    matches, cache = fuentes
    assert client.get('/grupos').json()['items'][0]['codigo'] == 'A'
    first = client.get('/grupos/A/posiciones').json()
    assert client.get('/grupos/A/posiciones').json() == first and list(cache) == ['grupos:v2:A']
    matches.assert_called_once_with('A')
    matches.return_value = [partido(goles=(0, 2))]
    assert client.get('/grupos/A/posiciones').json() == first
    assert invalidar_resultado('P-001', 'A')
    corrected = client.get('/grupos/A/posiciones').json()
    assert corrected['items'][0]['equipo']['codigo'] == 'BRA' and len(cache) == 1
    matches.return_value = [partido(estado='proximo')]
    invalidar_resultado('P-001', 'A')
    assert all(r['jugados'] == 0 for r in client.get('/grupos/A/posiciones').json()['items'])
    matches.return_value = [partido()]
    invalidar_resultado('P-001', 'A')
    assert client.get('/grupos/A/posiciones').json() == first


def test_http_errores_y_redis_opcional(client, fuentes, monkeypatch):
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/grupos/A/posiciones').status_code == 200
    assert client.get('/grupos/A/posiciones').status_code == 200
    assert mongo_adapter.find_grupo.call_count == 2
    mongo_adapter.find_grupo.reset_mock()
    assert client.get('/grupos/Z/posiciones').status_code == 400
    mongo_adapter.find_grupo.assert_not_called()
    monkeypatch.setattr(mongo_adapter, 'find_grupo', Mock(return_value=None))
    assert client.get('/grupos/A/posiciones').status_code == 404
    monkeypatch.setattr(mongo_adapter, 'list_grupos', Mock(side_effect=DatabaseUnavailableError('MongoDB')))
    assert client.get('/grupos').status_code == 503
    monkeypatch.setattr(mongo_adapter, 'list_grupos', Mock(return_value=[]))
    assert client.get('/grupos').json() == dict(items=[])


def test_dataset_cubre_64_selecciones_y_rechaza_catalogo_incompatible():
    teams, _ = inicio()
    docs = preparar(teams)
    assert len(docs) == 16 and sum(len(g['equipos']) for g in docs) == 64
    teams[0]['grupo'] = 'Z'
    with pytest.raises(ValueError): preparar(teams)


def test_reglas_cambiadas_y_cache_corrupta(client, fuentes, monkeypatch):
    _, cache = fuentes
    first = client.get('/grupos/A/posiciones').json()
    for key in cache: cache[key] = '{invalid'
    assert client.get('/grupos/A/posiciones').json() == first
    assert mongo_adapter.find_grupo.call_count == 2
    changed = deepcopy(G)
    changed['reglas']['victoria'] = 5
    monkeypatch.setattr(mongo_adapter, 'find_grupo', Mock(return_value=changed))
    borrar_cache_derivada(ClienteMemoria(cache))
    assert client.get('/grupos/A/posiciones').json()['items'][0]['puntos'] == 5
    assert len(cache) == 1


class ClienteMemoria:
    def __init__(self, cache):
        self.cache = cache

    def scan_iter(self, match, count):
        return iter([k for k in self.cache if fnmatchcase(k, match)])

    def delete(self, *keys):
        for key in keys:
            self.cache.pop(key, None)


def test_carga_masiva_borra_namespaces_derivados_con_scan(fuentes):
    _, cache = fuentes
    cache.update({k: '{}' for k in ('partido:v2:P-001', 'eventos:v2:P-001:50:0', 'alineaciones:v2:P-001',
                                    'grupos:v2:A', 'playoffs:v2:todos', 'mapa_calor:v2:P-001:ARG-10:todo:todo', 'ajena:abc', 'fixture:v1:todos')})
    borrar_cache_derivada(ClienteMemoria(cache))
    assert set(cache) == {'ajena:abc', 'fixture:v1:todos'}


def test_mongo_consulta_grupo_con_proyeccion_y_orden():
    from app.adapters.mongo_adapter import MongoAdapter
    adapter = MongoAdapter()
    adapter._db = MagicMock()
    adapter._client = Mock()
    collection = adapter._db.__getitem__.return_value
    collection.find.return_value.sort.return_value = []
    assert adapter.list_partidos_grupo('A') == []
    assert collection.find.call_args.args[0] == {'grupo': 'A', 'fase': 'Grupos'}
    assert 'sede' not in collection.find.call_args.args[1]
    collection.find.return_value.sort.assert_called_once_with([('fecha_hora', 1), ('_id', 1)])


def test_carga_grupos_solo_inserta_sin_tocar_resultados():
    from scripts.cargar_grupos import cargar
    db = Mock()
    docs = preparar(inicio()[0])
    cargar(db, docs)
    ops = db.grupos.bulk_write.call_args.args[0]
    assert len(ops) == 16
    assert all(op._doc == {'$setOnInsert': doc} for op, doc in zip(ops, docs))
    assert db.partidos.method_calls == [
        call.create_index(
            [('grupo', 1), ('fase', 1), ('fecha_hora', 1), ('_id', 1)], name='idx_partidos_grupo_fecha')]
