#!/usr/bin/env python3
"""Carga explícita de alineaciones: conserva las existentes salvo --reemplazar."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.alineaciones import Alineaciones


class Entrada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    partido: str = Field(pattern=r'^P-[0-9]{3}$')
    alineaciones: Alineaciones


class Lote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    partidos: list[Entrada] = Field(min_length=1)

    @model_validator(mode='after')
    def sin_duplicados(self):
        if len({p.partido for p in self.partidos}) != len(self.partidos):
            raise ValueError('Partido repetido')
        return self


def preparar(lote, partidos, jugadores):
    """Valida TODO antes de escribir; no inventa convocatorias desde el plantel."""
    catalogo = {j['_id']: j for j in jugadores}
    encuentros = {p['_id']: p for p in partidos}
    docs = []
    for entrada in lote.partidos:
        partido = encuentros.get(entrada.partido)
        if partido is None:
            raise ValueError('Partido inexistente')
        for lado in ('local', 'visitante'):
            alineacion = getattr(entrada.alineaciones, lado)
            if alineacion is None:
                continue
            equipo = partido.get(lado)
            if equipo is None or alineacion.equipo.model_dump() != equipo:
                raise ValueError('La selección no coincide con la plaza del partido')
            for jugador in alineacion.titulares + alineacion.suplentes:
                referencia = catalogo.get(jugador.codigo)
                if referencia is None or referencia['equipo']['_id'] != equipo['codigo']:
                    raise ValueError('Jugador inexistente o de otra selección')
        docs.append(entrada)
    return docs


def cargar(db, docs, reemplazar=False):
    # CAS: una ejecución simultánea no puede sobrescribir una alineación nueva.
    # No modifica marcador, reloj, estado ni otras entradas del partido.
    actualizados = 0
    for entrada in docs:
        filtro = {'_id': entrada.partido}
        if not reemplazar:
            filtro['alineaciones'] = None
        result = db.partidos.update_one(filtro, {'$set': {'alineaciones': entrada.alineaciones.model_dump()}})
        actualizados += result.modified_count
    return {'actualizados': actualizados, 'conservados': len(docs) - actualizados}


def main(archivo_default=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if archivo_default is None:
        parser.add_argument('archivo', type=Path)
    else:
        parser.add_argument('archivo', type=Path, nargs='?', default=archivo_default)
    parser.add_argument('--solo-validar', action='store_true', help='Valida estructura sin conectar a MongoDB')
    parser.add_argument('--reemplazar', action='store_true', help='Reemplaza convocatorias existentes de los partidos indicados')
    args = parser.parse_args()
    lote = Lote.model_validate_json(args.archivo.read_text())
    if args.solo_validar:
        print(json.dumps({'validados': len(lote.partidos), 'referencias_verificadas': False}))
        return
    from app.config.settings import settings
    from pymongo import MongoClient
    with MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=5000) as client:
        db = client[settings.mongo_database]
        docs = preparar(lote, list(db.partidos.find({}, {'_id': 1, 'local': 1, 'visitante': 1})),
                        list(db.jugadores.find({}, {'_id': 1, 'equipo._id': 1})))
        # Aplicación explícita del validador compatible con alineaciones.
        validator = json.loads((ROOT / 'data/fixture/partidos-validator.json').read_text())
        db.command('collMod', 'partidos', validator=validator, validationLevel='strict', validationAction='error')
        print(json.dumps(cargar(db, docs, args.reemplazar)))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Carga interrumpida: {type(exc).__name__}. Revisar archivo, referencias y conectividad.', file=sys.stderr)
        sys.exit(1)
