"""Detalle HTTP, reloj y correcciones: sin escrituras ni motores reales."""
from datetime import datetime
from unittest.mock import Mock, MagicMock

import pytest
from pymongo.errors import NetworkTimeout

from app.adapters import mongo_adapter, redis_adapter, neo4j_adapter
from app.adapters.mongo_adapter import MongoAdapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.fixture import PartidoFixture
from scripts.cargar_fixture import cargar


@pytest.fixture
def fuentes(monkeypatch):
    documento = dict(_id='P-001', fecha_hora=datetime(2030, 6, 9, 1, 30), fase='Grupos', grupo='A',
                     local=dict(codigo='URU', nombre='Uruguay'), visitante=dict(codigo='ESP', nombre='España'),
                     sede=dict(codigo='S-01', nombre='Centenario', ciudad='Montevideo'), estado='proximo', resultado=None)
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(side_effect=lambda _: documento))
    monkeypatch.setattr(neo4j_adapter, 'find_partido', Mock(side_effect=AssertionError('No usar Neo4j')))
    cache = {}
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(side_effect=lambda k: cache.get(k)))
    monkeypatch.setattr(redis_adapter, 'set_cache', Mock(side_effect=lambda k, v, t: cache.update({k: v})))
    return documento, cache


def test_proximo_datos_completos_y_cache(client, fuentes):
    doc, cache = fuentes
    response = client.get('/partidos/P-001', headers={'X-Request-Id': 'uno'})
    assert response.status_code == 200
    data = response.json()
    assert data['fecha_hora'] == '2030-06-09T01:30:00Z'
    assert data['fecha'] == '2030-06-09' and data['sede']['nombre'] == 'Centenario'
    assert data['estado'] == 'proximo' and data['resultado'] is None and data['reloj'] is None
    cached = client.get('/partidos/P-001', headers={'X-Request-Id': 'dos'})
    assert cached.json() == data and cached.headers['X-Request-Id'] == 'dos'
    assert len(cache) == 1 and 'requestId' not in next(iter(cache.values()))


def test_reloj_pausas_cierre_y_correccion_invalidan_cache(client, fuentes):
    doc, cache = fuentes
    client.get('/partidos/P-001')
    for periodo, minuto, adicional in [('primer_tiempo', 45, 2), ('entretiempo', 45, 0),
                                       ('segundo_tiempo', 62, 0), ('pausa', 62, 0)]:
        doc.update(estado='en_vivo', resultado=dict(goles_local=1, goles_visitante=1),
                   reloj=dict(periodo=periodo, minuto=minuto, adicional=adicional))
        data = client.get('/partidos/P-001').json()
        assert data['reloj'] == doc['reloj']
    doc.update(estado='finalizado', resultado=dict(goles_local=1, goles_visitante=1,
               penales=dict(goles_local=4, goles_visitante=3)))
    assert client.get('/partidos/P-001').json()['resultado']['penales']['goles_local'] == 4
    doc['resultado']['penales']['goles_local'] = 5
    assert client.get('/partidos/P-001').json()['resultado']['penales']['goles_local'] == 5
    assert len(cache) == 7


@pytest.mark.parametrize('cached', ['invalid', '{}', '[]', '{"codigo":"P-001"}'])
def test_cache_invalida_reconstruida(client, fuentes, monkeypatch, cached):
    monkeypatch.setattr(redis_adapter, 'get_cache', Mock(return_value=cached))
    assert client.get('/partidos/P-001').status_code == 200
    redis_adapter.set_cache.assert_called_once()


def test_redis_opcional_y_minuto_desconocido(client, fuentes, monkeypatch):
    doc, _ = fuentes
    doc.update(estado='en_vivo', resultado=dict(goles_local=0, goles_visitante=0))
    for method in ('get_cache', 'set_cache'):
        monkeypatch.setattr(redis_adapter, method, Mock(side_effect=DatabaseUnavailableError('Redis')))
    assert client.get('/partidos/P-001').json()['reloj'] is None


def test_no_ocultar_borrados_ni_caidas_con_cache(client, fuentes, monkeypatch):
    client.get('/partidos/P-001')
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(return_value=None))
    assert client.get('/partidos/P-001').status_code == 404
    monkeypatch.setattr(mongo_adapter, 'find_partido', Mock(side_effect=DatabaseUnavailableError('MongoDB', NetworkTimeout('secret'))))
    response = client.get('/partidos/P-001')
    assert response.status_code == 504 and response.json()['code'] == 'MONGODB_TIMEOUT'
    assert 'secret' not in response.text


def test_codigo_invalido_no_consulta(client, fuentes):
    assert client.get('/partidos/INVALID').status_code == 400
    mongo_adapter.find_partido.assert_not_called()


def test_detalle_reutiliza_plazas_y_revoca_resultado_obsoleto(client, fuentes, monkeypatch):
    doc, _ = fuentes
    doc.update(fase='Final', grupo=None)
    cruce = dict(_id='P-001', fase='Final', orden=1,
                 local=dict(tipo='equipo', equipo=doc['local'].copy()),
                 visitante=dict(tipo='equipo', equipo=doc['visitante'].copy()))
    monkeypatch.setattr(mongo_adapter, 'list_cruces', lambda: [cruce])
    monkeypatch.setattr(mongo_adapter, 'list_grupos', lambda: [])
    monkeypatch.setattr(mongo_adapter, 'list_fixture', lambda: [{k: v for k, v in doc.items() if k in PartidoFixture.model_fields or k == '_id'}])
    data = client.get('/partidos/P-001').json()
    assert data['local']['codigo'] == 'URU' and data['origen_local'] == 'Uruguay'
    doc.update(estado='finalizado', resultado=dict(goles_local=2, goles_visitante=1),
               reloj=dict(periodo='segundo_tiempo', minuto=90))
    assert client.get('/partidos/P-001').json()['resultado']['goles_local'] == 2
    cruce['local']['equipo'] = dict(codigo='ARG', nombre='Argentina')
    data = client.get('/partidos/P-001').json()
    assert data['local']['codigo'] == 'ARG' and data['requiere_revision']
    assert data['estado'] == 'proximo' and data['resultado'] is None and data['reloj'] is None


def test_adaptador_no_lee_eventos_ni_alineaciones():
    adapter = MongoAdapter()
    adapter._db = MagicMock()
    adapter._client = Mock()
    adapter.find_partido('P-001')
    filtro, projection = adapter._db.__getitem__.return_value.find_one.call_args.args
    assert filtro == {'_id': 'P-001'}
    assert projection['reloj'] == projection['sede'] == 1
    assert 'eventos' not in projection and 'alineaciones' not in projection


def test_recarga_conserva_reloj_y_reinicio_explicito_lo_reemplaza(fuentes):
    doc, _ = fuentes
    doc.update(reloj=dict(periodo='segundo_tiempo', minuto=70, adicional=0))
    for reiniciar in (False, True):
        db = Mock()
        db.list_collection_names.return_value = ['partidos']
        cargar(db, [doc], reiniciar=reiniciar)
        update = db.partidos.bulk_write.call_args.args[0][0]._doc
        assert ('reloj' in update['$set']) == reiniciar
        assert (update['$set'] if reiniciar else update['$setOnInsert'])['reloj'] == doc['reloj']
