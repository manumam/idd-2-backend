#!/usr/bin/env python3
"""Carga explícita del cuadro; nunca modifica participantes ni resultados de partidos."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.schemas.fixture import PartidoFixture
from app.schemas.grupos import Grupo
from app.schemas.playoffs import Cruce
from app.services.playoffs_service import validar_cruces


def preparar(partidos, grupos, archivo=ROOT / 'data/fixture/cruces.json'):
    cruces = [Cruce(codigo=d['_id'], **{k:v for k,v in d.items() if k != '_id'})
              for d in json.loads(archivo.read_text())['cruces']]
    ps = {d['_id']: PartidoFixture(codigo=d['_id'], **{k:v for k,v in d.items() if k in PartidoFixture.model_fields and k != 'codigo'}) for d in partidos}
    gs = {d['_id']: Grupo(codigo=d['_id'], **{k:v for k,v in d.items() if k in Grupo.model_fields and k != 'codigo'}) for d in grupos}
    ordenados = validar_cruces(cruces, ps, gs)
    if {c.codigo for c in cruces} != {p.codigo for p in ps.values() if p.fase != 'Grupos'}:
        raise ValueError('El cuadro debe cubrir todos los partidos eliminatorios')
    return [dict(_id=c.codigo, **c.model_dump(exclude={'codigo'})) for c in ordenados]


def cargar(db, documentos):
    from pymongo import UpdateOne
    # No sobreescribir reglas existentes silenciosamente.
    existentes = list(db.cruces.find({}, {'_id': 1, 'fase': 1, 'orden': 1, 'local': 1, 'visitante': 1}))
    por_id = {d['_id']: d for d in documentos}
    if any(por_id.get(d['_id']) != d for d in existentes):
        raise ValueError('El cuadro existente no coincide con el dataset')
    db.cruces.create_index([('fase', 1), ('orden', 1)], unique=True, name='idx_cruces_fase_orden')
    return db.cruces.bulk_write([UpdateOne({'_id': d['_id']}, {'$setOnInsert': d}, upsert=True) for d in documentos])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-validar', action='store_true')
    args = parser.parse_args()
    if args.solo_validar:
        from scripts.cargar_fixture import preparar as fixture, DATA
        from scripts.cargar_grupos import preparar as grupos
        from scripts.cargar_inicio_mundial import preparar as inicio
        docs = preparar(fixture(DATA / 'import', DATA / 'fixture-calendario.json'), grupos(inicio()[0]))
        print(json.dumps(dict(cruces=len(docs))))
        return
    from app.config.settings import settings
    from pymongo import MongoClient
    from redis.exceptions import RedisError
    from app.services.cache_partidos import borrar_cache_derivada, conectar_cache
    with MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000) as client:
        db = client[settings.mongo_database]
        docs = preparar(list(db.partidos.find()), list(db.grupos.find()))
        try:
            result = cargar(db, docs)
        finally:
            try:
                with conectar_cache(settings) as cache:
                    borrar_cache_derivada(cache)
            except RedisError:
                print('Advertencia: no se pudo invalidar la caché; esperar su TTL.', file=sys.stderr)
        print(json.dumps(dict(insertados=result.upserted_count)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Carga de playoffs interrumpida: {type(exc).__name__}. Revisar datos y conectividad.', file=sys.stderr)
        sys.exit(1)
