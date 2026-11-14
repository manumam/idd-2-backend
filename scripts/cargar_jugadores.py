#!/usr/bin/env python3
"""Carga explícita de jugadores de 2026; no importa equipos, partidos ni resultados."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / 'data/worldcup2026'
POSICIONES = {'GK': 'Arquero', 'DF': 'Defensor', 'MF': 'Mediocampista', 'FW': 'Delantero'}


def preparar(data_dir=DATA):
    source = data_dir / 'source/players.tsv'
    provenance = json.loads((data_dir / 'players-provenance.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != provenance['sha256']:
        raise ValueError('El TSV no coincide con el snapshot documentado')
    teams = {t['fifa_code']: t['name'] for t in json.loads((data_dir / 'source/worldcup.teams.json').read_text())}
    docs = []
    seen = set()
    with source.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            match = re.search(r'\(([A-Z]{3})\)$', row['Team'])
            if not match or match[1] not in teams:
                raise ValueError('Equipo inexistente en el catálogo de origen')
            team = match[1]
            dorsal = int(row['#'])
            code = f'{team}-{dorsal}'
            if not 1 <= dorsal <= 99 or code in seen:
                raise ValueError('Dorsal inválido o duplicado dentro del equipo')
            seen.add(code)
            name, surname = row['FIRST NAME(S)'].strip(), row['LAST NAME(S)'].strip()
            # Preserve mononyms as provided by the source; do not invent surnames.
            if not name and not surname:
                raise ValueError('Jugador sin nombre')
            birth = datetime.strptime(row['DOB'], '%d/%m/%Y')
            if birth >= datetime(2026, 6, 11):
                raise ValueError('Fecha de nacimiento posterior al inicio del torneo')
            if row['POS'] not in POSICIONES:
                raise ValueError('Posición desconocida')
            docs.append(dict(_id=code, nombre=name, apellido=surname, dorsal=dorsal,
                             posicion=POSICIONES[row['POS']], fecha_nacimiento=birth,
                             club=row['CLUB'].strip() or None,
                             equipo={'_id': team, 'nombre': teams[team]},
                             fuente={'edicion': 2026, 'repository': provenance['repository'],
                                     'commit': provenance['commit']}))
    counts = Counter(d['equipo']['_id'] for d in docs)
    if set(counts) != set(teams) or len(docs) != 1248 or set(counts.values()) != {26}:
        raise ValueError('El snapshot debe cubrir 48 planteles de 26 jugadores')
    return docs


def cargar(db, docs):
    from pymongo import UpdateOne
    # Existing captain flags and fields outside the source are preserved.
    operations = [UpdateOne({'_id': d['_id']}, {'$set': {k: v for k, v in d.items() if k != '_id'}}, upsert=True) for d in docs]
    db.jugadores.create_index([('equipo._id', 1), ('dorsal', 1)], name='idx_jugadores_equipo_dorsal')
    db.jugadores.create_index([('equipo._id', 1), ('posicion', 1)], name='idx_jugadores_equipo_posicion')
    result = db.jugadores.bulk_write(operations, ordered=True)
    return dict(insertados=result.upserted_count, actualizados=result.modified_count, coincidentes=result.matched_count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-validar', action='store_true')
    args = parser.parse_args()
    docs = preparar()
    if args.solo_validar:
        print(json.dumps({'validados': len(docs), 'equipos_referenciados': 48}))
        return
    from app.config.settings import settings
    from pymongo import MongoClient
    with MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000,
                     connectTimeoutMS=5000, socketTimeoutMS=5000) as client:
        print(json.dumps(cargar(client[settings.mongo_database], docs)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Driver messages may contain connection credentials; report only safe types.
        print(f'Carga de jugadores interrumpida: {type(exc).__name__}.', file=sys.stderr)
        sys.exit(1)
