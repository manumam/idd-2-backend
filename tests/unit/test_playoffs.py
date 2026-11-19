from unittest.mock import Mock
import pytest
from app.adapters import mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.fixture import PartidoFixture
from app.schemas.grupos import Grupo
from app.schemas.playoffs import Cruce
from app.services.cache_partidos import invalidar_resultado
from app.services.playoffs_service import resolver, validar_cruces
from scripts.cargar_playoffs import preparar, cargar
from scripts.cargar_fixture import preparar as fixture, DATA
from scripts.cargar_grupos import preparar as grupos
from scripts.cargar_inicio_mundial import preparar as inicio


def datos():
    ps = fixture(DATA / 'import', DATA / 'fixture-calendario.json')
    gs = grupos(inicio()[0])
    cs = preparar(ps, gs)
    return cs, ps, gs


def modelos(cs, ps, gs):
    def modelo(cls, d):
        return cls(codigo=d['_id'], **{k:v for k,v in d.items() if k in cls.model_fields and k != 'codigo'})
    return ([modelo(Cruce, d) for d in cs], {d['_id']: modelo(PartidoFixture,d) for d in ps}, {d['_id']: modelo(Grupo,d) for d in gs})


def finalizar_grupos(ps):
    for p in ps:
        if p['fase'] == 'Grupos':
            p.update(estado='finalizado', resultado=dict(goles_local=0, goles_visitante=0))


def test_dataset_origenes_y_grupos_incompletos():
    cs, ps, gs = datos()
    r = resolver(*modelos(cs, ps, gs))
    assert len(r.items) == 31
    assert r.items[0].local.descripcion == '1.º del grupo A'
    assert r.items[16].local.descripcion == 'Ganador del partido P-097'
    assert all(c.ganador is None and c.local.equipo is None for c in r.items)
    assert r.items[0].siguiente == 'P-113' and r.items[-1].siguiente is None


def test_torneo_completo_penales_idempotencia_y_correccion():
    cs, ps, gs = datos()
    finalizar_grupos(ps)
    por_id = {p['_id']:p for p in ps}
    for fase in ['Dieciseisavos', 'Octavos', 'Cuartos', 'Semifinal', 'Final']:
        r = resolver(*modelos(cs, ps, gs))
        for c in r.items:
            if c.fase == fase:
                por_id[c.codigo].update(local=c.local.equipo.model_dump(), visitante=c.visitante.equipo.model_dump(), estado='finalizado',
                    resultado=dict(goles_local=1, goles_visitante=1, penales=dict(goles_local=5, goles_visitante=4)))
    original = resolver(*modelos(cs, ps, gs))
    assert all(c.ganador is not None and not c.requiere_revision for c in original.items)
    assert resolver(*modelos(cs, ps, gs)) == original
    por_id['P-097']['resultado']['penales'] = dict(goles_local=3, goles_visitante=4)
    cambiado = resolver(*modelos(cs, ps, gs))
    assert cambiado.items[0].ganador != original.items[0].ganador
    siguientes = {c.codigo:c for c in cambiado.items}
    for codigo in ['P-113', 'P-121', 'P-125', 'P-127']:
        assert siguientes[codigo].requiere_revision
        assert siguientes[codigo].ganador is None and siguientes[codigo].partido.resultado is None
    assert siguientes['P-114'].ganador == original.items[17].ganador
    # No modifica resultados originales: quedan disponibles para revisión.
    assert por_id['P-113']['estado'] == 'finalizado'


def test_correccion_de_grupo_revoca_participante_y_resultado():
    cs, ps, gs = datos()
    finalizar_grupos(ps)
    r = resolver(*modelos(cs, ps, gs))
    c = r.items[0]
    p = next(p for p in ps if p['_id']==c.codigo)
    p.update(local=c.local.equipo.model_dump(), visitante=c.visitante.equipo.model_dump(), estado='finalizado', resultado=dict(goles_local=2,goles_visitante=1))
    assert resolver(*modelos(cs,ps,gs)).items[0].ganador is not None
    next(p for p in ps if p['grupo']=='A').update(estado='proximo',resultado=None)
    corrected = resolver(*modelos(cs,ps,gs)).items[0]
    assert corrected.local.equipo is None and corrected.ganador is None and corrected.requiere_revision


@pytest.mark.parametrize('resultado,valido', [
    (dict(goles_local=2,goles_visitante=1), True),
    (dict(goles_local=1,goles_visitante=1), False),
    (dict(goles_local=1,goles_visitante=1,penales=dict(goles_local=4,goles_visitante=4)), False),
    (dict(goles_local=2,goles_visitante=1,penales=dict(goles_local=4,goles_visitante=5)), False),
])
def test_desempate_valido(resultado,valido):
    cs,ps,gs=datos(); finalizar_grupos(ps)
    c=resolver(*modelos(cs,ps,gs)).items[0]
    p=next(p for p in ps if p['_id']==c.codigo)
    p.update(local=c.local.equipo.model_dump(), visitante=c.visitante.equipo.model_dump(), estado='finalizado', resultado=resultado)
    r=resolver(*modelos(cs,ps,gs)).items[0]
    assert (r.ganador is not None) == valido
    assert r.requiere_revision != valido


@pytest.mark.parametrize('mutacion', ['ciclo','huerfano','duplicado','plaza','fase','grupo','sin_final'])
def test_rechaza_dataset_invalido(mutacion):
    cs,ps,gs=modelos(*datos())
    if mutacion=='ciclo': cs[0].local=cs[16].local.model_copy(update={'cruce':'P-127'})
    if mutacion=='huerfano': cs[16].local.cruce='P-999'
    if mutacion=='duplicado': cs.append(cs[0])
    if mutacion=='plaza': cs[1].local=cs[0].local
    if mutacion=='fase': cs[0].fase='Final'
    if mutacion=='grupo': gs.pop('A')
    if mutacion=='sin_final': cs.pop()
    with pytest.raises(ValueError): validar_cruces(cs,ps,gs)


def test_http_cache_correcciones_vacio_y_fallos(client,monkeypatch,cache_redis):
    cs,ps,gs=datos()
    monkeypatch.setattr(mongo_adapter,'list_cruces',Mock(return_value=cs))
    monkeypatch.setattr(mongo_adapter,'list_fixture',Mock(return_value=[{k:v for k,v in p.items() if k in PartidoFixture.model_fields or k=='_id'} for p in ps]))
    monkeypatch.setattr(mongo_adapter,'list_grupos',Mock(return_value=gs))
    cache=cache_redis
    first=client.get('/playoffs')
    assert first.status_code==200
    assert client.get('/playoffs').json()==first.json() and list(cache)==['playoffs:v2:todos']
    mongo_adapter.list_fixture.assert_called_once()
    redis_adapter.set_cache.assert_called_once()
    finalizar_grupos(mongo_adapter.list_fixture.return_value)
    assert client.get('/playoffs').json()==first.json()
    cache['partido:v2:P-097']='{}'
    assert invalidar_resultado('P-001','A')
    assert 'partido:v2:P-097' not in cache
    assert client.get('/playoffs').json()['items'][0]['local']['equipo'] is not None and len(cache)==1
    for k in cache: cache[k]='invalid'
    assert client.get('/playoffs').status_code==200
    for method in ['get_cache','set_cache']:
        monkeypatch.setattr(redis_adapter,method,Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/playoffs').status_code==200
    monkeypatch.setattr(mongo_adapter,'list_cruces',Mock(return_value=[]))
    assert client.get('/playoffs').json()=={'items':[]}
    monkeypatch.setattr(mongo_adapter,'list_cruces',Mock(side_effect=DatabaseUnavailableError('MongoDB')))
    assert client.get('/playoffs').status_code==503


def test_carga_aditiva_sin_tocar_partidos():
    cs,_,_=datos()
    db=Mock(); db.cruces.find.return_value=[]
    cargar(db,cs)
    ops=db.cruces.bulk_write.call_args.args[0]
    assert all(o._doc=={'$setOnInsert':d} for o,d in zip(ops,cs))
    assert not db.partidos.mock_calls
    db.cruces.find.return_value=[dict(cs[0], orden=99)]
    db.cruces.bulk_write.reset_mock()
    with pytest.raises(ValueError): cargar(db,cs)
    db.cruces.bulk_write.assert_not_called()
