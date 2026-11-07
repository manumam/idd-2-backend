"""Opt-in: MongoDB y Redis aislados; no usa ni detiene bases existentes.

FIXTURE_INTEGRATION=1 FIXTURE_DATA_ROOT=/ruta/al/tp
FIXTURE_TEST_MONGO_URI=mongodb://127.0.0.1:47017 FIXTURE_TEST_REDIS_PORT=46379
"""
import importlib.util
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError
from redis import Redis

from app.adapters import mongo_adapter, redis_adapter
from app.config.settings import settings
from app.schemas.fixture import FixtureResponse
from app.services.fixture_service import FIXTURE_CACHE_KEY, invalidar_fixture

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv('FIXTURE_INTEGRATION') != '1', reason='Requiere MongoDB y Redis aislados de fixture'
)]


@pytest.fixture
def lab(monkeypatch):
    root = Path(os.environ['FIXTURE_DATA_ROOT']) / 'fixture2030-mongo'
    spec = importlib.util.spec_from_file_location('fixture_seed', root / 'scripts/cargar_fixture.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    mongo = MongoClient(os.environ['FIXTURE_TEST_MONGO_URI'], serverSelectionTimeoutMS=2000,
                        socketTimeoutMS=2000, tz_aware=True)
    name = 'fixture_test_' + uuid4().hex
    db = mongo[name]
    redis = Redis(host='127.0.0.1', port=int(os.environ['FIXTURE_TEST_REDIS_PORT']),
                  decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
    monkeypatch.setattr(mongo_adapter, 'connect', lambda: db)
    monkeypatch.setattr(redis_adapter, 'get_client', lambda: redis)
    docs = seed.preparar(root.parent / 'fixture2030-neo4j/import', root / 'datos/fixture-calendario.json')
    redis.delete(FIXTURE_CACHE_KEY)
    try:
        yield seed, root, db, docs, redis
    finally:
        redis.delete(FIXTURE_CACHE_KEY)
        mongo.drop_database(name)
        mongo.close()
        redis.close()


def test_seed_idempotency_preservation_and_reset(lab):
    seed, root, db, docs, _ = lab
    assert seed.cargar(db, docs)['insertados'] == 127
    score = dict(goles_local=3, goles_visitante=1, penales=None)
    db.partidos.update_one({'_id': 'P-001'}, {'$set': dict(estado='finalizado', resultado=score)})
    assert seed.cargar(db, docs)['insertados'] == 0
    assert db.partidos.count_documents({}) == 127
    assert db.partidos.find_one({'_id': 'P-001'})['resultado'] == score
    demo = seed.preparar(root.parent / 'fixture2030-neo4j/import', root / 'datos/fixture-calendario.json',
                        root / 'datos/fixture-escenario-demo.json')
    seed.cargar(db, demo, reiniciar=True)
    assert {d['estado'] for d in db.partidos.find()} == {'proximo', 'en_vivo', 'finalizado'}


def test_validator_and_index(lab):
    seed, _, db, docs, _ = lab
    seed.cargar(db, docs)
    for update in ({'estado': 'invalido'}, {'fecha_hora': '2030-06-08'},
                   {'estado': 'finalizado', 'resultado': dict(goles_local=-1, goles_visitante=0)},
                   {'estado': 'en_vivo', 'resultado': None}):
        with pytest.raises(WriteError):
            db.partidos.update_one({'_id': 'P-001'}, {'$set': update})
    explanation = db.partidos.find().sort([('fecha_hora', 1), ('_id', 1)]).explain()
    plan = json.dumps(explanation['queryPlanner']['winningPlan'])
    assert 'idx_partidos_fecha_codigo' in plan
    assert '"stage": "SORT"' not in plan


def test_api_order_cache_ttl_and_invalidation(client, lab, monkeypatch):
    seed, _, db, docs, cache = lab
    seed.cargar(db, list(reversed(docs)))
    monkeypatch.setattr(settings, 'fixture_cache_ttl_seconds', 1)
    first = client.get('/fixture')
    assert first.status_code == 200
    items = first.json()['items']
    assert len(items) == 127
    assert [(p['fecha_hora'], p['codigo']) for p in items] == sorted((p['fecha_hora'], p['codigo']) for p in items)
    assert 0 < cache.pttl(FIXTURE_CACHE_KEY) <= 1000
    db.partidos.update_one({'_id': 'P-001'}, {'$set': dict(estado='en_vivo', resultado=dict(goles_local=1, goles_visitante=0))})
    assert client.get('/fixture').json() == first.json()
    assert invalidar_fixture()
    assert client.get('/fixture').json()['items'][0]['estado'] == 'en_vivo'
    time.sleep(1.1)
    assert not cache.exists(FIXTURE_CACHE_KEY)
    assert client.get('/fixture').status_code == 200


def test_real_redis_bad_payload(client, lab):
    seed, _, db, docs, cache = lab
    seed.cargar(db, docs)
    cache.set(FIXTURE_CACHE_KEY, '{"wrong":true}', ex=5)
    assert client.get('/fixture').status_code == 200
    assert len(FixtureResponse.model_validate_json(cache.get(FIXTURE_CACHE_KEY)).items) == 127


def test_real_unreachable_redis(client, lab, monkeypatch):
    """Socket reservado sin listener: rechazo real, sin detener servicios."""
    import socket
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    seed, _, db, docs, _ = lab
    seed.cargar(db, docs)
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        unavailable = Redis(host='127.0.0.1', port=reserved.getsockname()[1],
                            socket_timeout=0.1, socket_connect_timeout=0.1,
                            retry=Retry(NoBackoff(), 0))
        monkeypatch.setattr(redis_adapter, 'get_client', lambda: unavailable)
        try:
            response = client.get('/fixture')
            assert response.status_code == 200
            assert len(response.json()['items']) == 127
        finally:
            unavailable.close()


def test_real_unreachable_mongo_hit_and_miss(client, lab, monkeypatch):
    import socket
    seed, _, db, docs, cache = lab
    seed.cargar(db, docs)
    assert client.get('/fixture').status_code == 200
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        unavailable = MongoClient(host='127.0.0.1', port=reserved.getsockname()[1],
                                  serverSelectionTimeoutMS=100, connectTimeoutMS=100, socketTimeoutMS=100)
        monkeypatch.setattr(mongo_adapter, 'connect', lambda: unavailable['fixture_unavailable'])
        try:
            assert client.get('/fixture').status_code == 200
            cache.delete(FIXTURE_CACHE_KEY)
            response = client.get('/fixture', headers={'X-Request-Id': 'fixture-down'})
            assert response.status_code == 504
            assert response.json()['code'] == 'MONGODB_TIMEOUT'
            assert response.json()['requestId'] == response.headers['X-Request-Id'] == 'fixture-down'
            assert not cache.exists(FIXTURE_CACHE_KEY)
        finally:
            unavailable.close()
