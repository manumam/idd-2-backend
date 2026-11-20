#!/usr/bin/env python3
"""Registro explícito de cobertura y consolidación del caso 9. Nunca carga tracking."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.adapters import mongo_adapter, influx_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.rendimiento import ControlTracking
from app.services.partidos_service import _detalle_documento
from app.services.rendimiento_service import _control, consolidar_jugadores, participantes


def registrar_control(codigo, control, reemplazar=False):
    doc = mongo_adapter.find_estadisticas(codigo)
    if not doc:
        raise ValueError('Partido inexistente')
    raw = control.model_dump(mode='json')
    _control({**doc, 'tracking_control': raw}, _detalle_documento(doc))
    refs = participantes(doc, _detalle_documento(doc))
    if set(refs) - set(control.jugadores):
        raise ValueError('El control debe declarar todos los convocados y protagonistas conocidos')
    for jugador in control.jugadores:
        if not mongo_adapter.find_jugador(jugador):
            raise ValueError('El control contiene un jugador inexistente')
    existente = doc.get('tracking_control')
    equivalente = existente is not None and ControlTracking.model_validate(existente) == control
    if existente and not equivalente and not reemplazar:
        raise ValueError('Ya existe otro control: revisar y usar --reemplazar-control explícitamente')
    if equivalente:
        return
    if not mongo_adapter.guardar_control_tracking(codigo, doc, raw):
        raise ValueError('El partido cambió; reintentar')
    try:
        redis_adapter.delete_cache_matching('rendimiento:v1:*')
        redis_adapter.delete_cache_matching('acumulados:v1:*')
    except DatabaseUnavailableError:
        # La huella de entradas cambia; no depende de Redis para publicar.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partido', required=True)
    accion = parser.add_mutually_exclusive_group(required=True)
    accion.add_argument('--registrar-control', type=Path)
    accion.add_argument('--consolidar', action='store_true')
    accion.add_argument('--actualizar-validador', action='store_true')
    parser.add_argument('--reemplazar-control', action='store_true')
    parser.add_argument('--solo-validar', action='store_true', help='Valida el archivo sin conectar a bases')
    args = parser.parse_args()
    if not re.fullmatch(r'P-[0-9]{3}', args.partido):
        parser.error('Código de partido inválido')
    if args.solo_validar and not args.registrar_control:
        parser.error('--solo-validar requiere --registrar-control')
    if args.reemplazar_control and not args.registrar_control:
        parser.error('--reemplazar-control requiere --registrar-control')
    if args.registrar_control:
        control = ControlTracking.model_validate_json(args.registrar_control.read_text())
        if not args.solo_validar:
            registrar_control(args.partido, control, args.reemplazar_control)
        print(json.dumps(dict(partido=args.partido, jugadores=len(control.jugadores),
            bases_modificadas=not args.solo_validar)))
    elif args.actualizar_validador:
        validator = json.loads((ROOT / 'data/fixture/partidos-validator.json').read_text())
        mongo_adapter.db.command('collMod', 'partidos', validator=validator,
            validationLevel='strict', validationAction='error')
        print('Validador de partidos actualizado; documentos deportivos conservados.')
    else:
        print(json.dumps(consolidar_jugadores(args.partido), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Operación interrumpida: {type(exc).__name__}. Revisar cobertura, referencias y conexiones.', file=sys.stderr)
        sys.exit(1)
    finally:
        mongo_adapter.close()
        influx_adapter.close()
        redis_adapter.close()
