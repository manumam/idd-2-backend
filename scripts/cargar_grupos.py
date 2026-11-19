#!/usr/bin/env python3
"""Carga explícita y aditiva de grupos; no modifica equipos ni resultados."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.schemas.grupos import Grupo


def preparar(equipos):
    catalogo = {e['_id']: e for e in equipos}
    docs = json.loads((ROOT / 'data/fixture/grupos.json').read_text())['grupos']
    grupos = []
    usados = set()
    for d in docs:
        if usados.intersection(d['equipos']):
            raise ValueError('Selección en más de un grupo')
        usados.update(d['equipos'])
        refs = []
        for code in d['equipos']:
            team = catalogo[code]
            if team['grupo'] != d['_id']:
                raise ValueError('El catálogo no coincide con el dataset de grupos')
            refs.append(dict(codigo=code, nombre=team['nombre']))
        grupo = Grupo(codigo=d['_id'], equipos=refs, reglas=d['reglas'])
        grupos.append(dict(_id=grupo.codigo, equipos=[e.model_dump() for e in grupo.equipos], reglas=grupo.reglas.model_dump()))
    return grupos


def cargar(db, grupos):
    from pymongo import UpdateOne
    db.partidos.create_index([('grupo', 1), ('fase', 1), ('fecha_hora', 1), ('_id', 1)], name='idx_partidos_grupo_fecha')
    return db.grupos.bulk_write([UpdateOne({'_id': g['_id']}, {'$setOnInsert': g}, upsert=True) for g in grupos])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-validar', action='store_true')
    args = parser.parse_args()
    if args.solo_validar:
        from scripts.cargar_inicio_mundial import preparar as inicio
        grupos = preparar(inicio()[0])
        print(json.dumps(dict(grupos=len(grupos))))
        return
    from app.config.settings import settings
    from pymongo import MongoClient
    from redis.exceptions import RedisError
    from app.services.cache_partidos import borrar_cache_derivada, conectar_cache
    with MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000) as client:
        db = client[settings.mongo_database]
        grupos = preparar(list(db.equipos.find({'_id': 1, 'nombre': 1, 'grupo': 1})))
        try:
            result = cargar(db, grupos)
        finally:
            # Las reglas de un grupo alteran sus posiciones, el cuadro y los cruces que derivan de él.
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
        print(f'Carga de grupos interrumpida: {type(exc).__name__}. Revisar catálogo y conectividad.', file=sys.stderr)
        sys.exit(1)
