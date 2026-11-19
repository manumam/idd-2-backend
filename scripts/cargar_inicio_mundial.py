#!/usr/bin/env python3
"""Inicio simulado 2030: 64 equipos, 16 grupos, 127 partidos sin disputar."""
import argparse
import csv
from pathlib import Path
import sys
import json
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.cargar_fixture import preparar as preparar_fixture, cargar as cargar_fixture, DATA


def preparar():
    with (DATA / 'import/equipos.csv').open() as stream:
        teams = list(csv.DictReader(stream))
    with (DATA / 'import/sedes.csv').open() as stream:
        venues = list(csv.DictReader(stream))
    normalize = lambda v: ''.join(c for c in unicodedata.normalize('NFD', v.casefold()) if not unicodedata.combining(c))
    hosts = {normalize(v['pais']) for v in venues}
    equipos = [dict(_id=t['id'], nombre=t['nombre'], confederacion=t['confederacion'],
                    grupo=t['grupo'], ranking_fifa=None, director_tecnico=None,
                    anfitrion=normalize(t['nombre']) in hosts) for t in teams]
    partidos = preparar_fixture(DATA / 'import', DATA / 'fixture-calendario.json')
    for partido in partidos:
        partido['estado'], partido['resultado'] = 'proximo', None
        if partido['fase'] != 'Grupos':
            partido['local'] = partido['visitante'] = None
    return equipos, partidos


def cargar(db, equipos, partidos):
    from pymongo import UpdateOne
    # Explicit initialization must never reset a tournament already in progress.
    if db.partidos.count_documents({}):
        raise ValueError('Ya existen partidos: no se reinicia ni mezcla un torneo existente')
    # Do not overwrite existing team metadata with unknown values.
    result = db.equipos.bulk_write([UpdateOne({'_id': t['_id']}, {'$setOnInsert': t}, upsert=True) for t in equipos])
    fixture = cargar_fixture(db, partidos)
    # Keep embedded names in existing players aligned with the simulated catalog.
    for team in equipos:
        db.jugadores.update_many({'equipo._id': team['_id']}, {'$set': {'equipo.nombre': team['nombre']}})
    return dict(equipos_insertados=result.upserted_count, partidos=fixture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-validar', action='store_true')
    args = parser.parse_args()
    equipos, partidos = preparar()
    if args.solo_validar:
        print(json.dumps(dict(equipos=len(equipos), partidos=len(partidos), eliminatorias_pendientes=sum(p['local'] is None for p in partidos))))
        return
    from app.config.settings import settings
    from pymongo import MongoClient
    from redis import Redis
    from redis.exceptions import RedisError
    from app.services.cache_partidos import borrar_cache_derivada
    with MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=5000) as client:
        result = cargar(client[settings.mongo_database], equipos, partidos)
    try:
        with Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
                   password=settings.redis_password or None, socket_connect_timeout=2, socket_timeout=2) as cache:
            cache.delete('fixture:v1:todos')
            borrar_cache_derivada(cache)
    except RedisError:
        print('Advertencia: no se pudo invalidar la caché; esperar su TTL.', file=sys.stderr)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Inicialización interrumpida: {type(exc).__name__}.', file=sys.stderr)
        sys.exit(1)
