#!/usr/bin/env python3
"""Plan explícito del caso 8: seed final o reproducción acelerada, sin borrar partidos."""
import argparse
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scripts.simular_partido import PlanPartido, crear_plan
from app.adapters import mongo_adapter, influx_adapter
from app.schemas.partidos import EquipoEvento
from app.services.comparacion_service import agregar_muestras, consolidar, instante
from app.services.seguimiento_service import aplicar_tick


class PlanEstadisticas(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(default=1, ge=1, le=1)
    inicio: str
    local: EquipoEvento
    visitante: EquipoEvento
    deportivo: PlanPartido

    @model_validator(mode='after')
    def validar(self):
        if self.inicio != instante(self.inicio).strftime('%Y-%m-%dT%H:%M:%SZ'):
            raise ValueError('Inicio UTC con precisión de segundos requerido')
        if self.local.codigo == self.visitante.codigo:
            raise ValueError('Equipos distintos requeridos')
        if not self.deportivo.ticks[-1].finalizado or self.deportivo.ticks[0].reloj.minuto != 0:
            raise ValueError('El plan debe cubrir desde minuto cero hasta cierre')
        if any(t.reloj.adicional for t in self.deportivo.ticks):
            raise ValueError('Este guion no admite tiempo adicional')
        if any(e.equipo not in (self.local, self.visitante) for t in self.deportivo.ticks for e in t.eventos):
            raise ValueError('Equipo ajeno en el guion')
        # El generador v1 tiene nueve ticks y cinco eventos: no acepta guiones alterados.
        firma = [(t.reloj.minuto, t.reloj.periodo, t.finalizado, [e.tipo for e in t.eventos]) for t in self.deportivo.ticks]
        esperada = [(0, 'primer_tiempo', False, []), (12, 'primer_tiempo', False, ['gol']),
            (28, 'primer_tiempo', False, ['tarjeta_amarilla']), (45, 'entretiempo', False, []),
            (46, 'segundo_tiempo', False, []), (62, 'segundo_tiempo', False, ['cambio']),
            (78, 'segundo_tiempo', False, ['gol']), (82, 'segundo_tiempo', False, ['tarjeta_roja']),
            (90, 'segundo_tiempo', True, [])]
        if firma != esperada:
            raise ValueError('Secuencia incompatible con el guion v1')
        for tick in self.deportivo.ticks:
            for e in tick.eventos:
                esperado = self.local if e.tipo in ('gol', 'cambio') else self.visitante
                if e.equipo != esperado or e.minuto != tick.reloj.minuto or e.adicional:
                    raise ValueError('Evento incompatible con el guion v1')
        return self

    def huella(self):
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def muestras(self, desde_segundo, hasta_segundo):
        inicio = instante(self.inicio)
        filas = []
        for segundo in range(desde_segundo, hasta_segundo + 1, 5):
            posesion = 55 + ((segundo // 300) % 5 - 2)
            for i, equipo in enumerate((self.local, self.visitante)):
                # Pases por intervalo, tiros acumulados; la primera muestra es la base cero.
                pases = 0 if segundo == 0 else (1 if (segundo // 5) % (3 if i == 0 else 4) == 0 else 0)
                filas.append(dict(time=(inicio + timedelta(seconds=segundo)).isoformat(),
                    equipo_id=equipo.codigo, posesion_pct=posesion if i == 0 else 100 - posesion,
                    tiros_acumulados=segundo * (14 if i == 0 else 7) // 5400,
                    pases_intervalo=pases, duracion_s=5 if segundo else 0))
        return filas

    def control(self, tick):
        segundo = self.deportivo.ticks[tick].reloj.minuto * 60 if tick >= 0 else 0
        return dict(plan=self.huella(), inicio=self.inicio,
            hasta=(instante(self.inicio) + timedelta(seconds=segundo)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            muestras=(segundo // 5 + 1) * 2 if tick >= 0 else 0,
            tick=tick, completa=tick == len(self.deportivo.ticks) - 1)


def line_protocol(plan, filas):
    return '\n'.join(
        f'estadisticas_partido,partido_id={plan.deportivo.partido},equipo_id={f["equipo_id"]} '
        f'posesion_pct={float(f["posesion_pct"])},tiros_acumulados={f["tiros_acumulados"]}i,'
        f'pases_intervalo={f["pases_intervalo"]}i,duracion_s={f["duracion_s"]}i '
        f'{int(instante(f["time"]).timestamp())}' for f in filas) + '\n'


def ejecutar(plan, intervalo):
    codigo = plan.deportivo.partido
    doc = mongo_adapter.find_estadisticas(codigo)
    if not doc or doc.get('local') != plan.local.model_dump() or doc.get('visitante') != plan.visitante.model_dump():
        raise ValueError('El plan no corresponde a los participantes actuales')
    if instante(doc['fecha_hora']) != instante(plan.inicio):
        raise ValueError('El horario del partido cambió')
    for tick in plan.deportivo.ticks:
        for evento in tick.eventos:
            for protagonista in evento.protagonistas:
                jugador = mongo_adapter.find_jugador(protagonista.jugador.codigo)
                if not jugador or jugador['equipo']['_id'] != evento.equipo.codigo:
                    raise ValueError('Jugador inexistente o de otra selección')
                nombre = f"{jugador['nombre']} {jugador.get('apellido', '')}".strip()
                if nombre != protagonista.jugador.nombre:
                    raise ValueError('La referencia de jugador cambió')
    control = doc.get('estadisticas_control')
    if control and control.get('plan') != plan.huella():
        raise ValueError('El partido pertenece a otro plan; no se reemplaza')
    if not control:
        if doc['estado'] != 'proximo' or doc.get('eventos') or doc.get('resultado'):
            raise ValueError('Elegir un partido próximo sin resultados ni eventos')
        # La lectura comprueba que no se sobrescriban muestras de otra carga.
        final = plan.control(len(plan.deportivo.ticks) - 1)
        if influx_adapter.find_muestras(codigo, plan.inicio, final['hasta']):
            raise ValueError('Ya existen muestras temporales; no se reemplazan')
    # Migración explícita del validador, solo en una ejecución autorizada.
    validator = json.loads((ROOT / 'data/fixture/partidos-validator.json').read_text())
    mongo_adapter.db.command('collMod', 'partidos', validator=validator,
        validationLevel='strict', validationAction='error')
    if not control:
        control = plan.control(-1)
        if not mongo_adapter.guardar_estadisticas(codigo, doc, {'estadisticas_control': control}):
            raise ValueError('El partido cambió antes de iniciar')
    if control != plan.control(control['tick']):
        raise ValueError('El avance persistido no coincide con el plan')
    inicio_tick = control['tick'] + 1
    for i in range(inicio_tick, len(plan.deportivo.ticks)):
        if i > inicio_tick:
            time.sleep(intervalo)
        tick = plan.deportivo.ticks[i]
        actual = mongo_adapter.find_estadisticas(codigo)
        if (not actual or actual.get('local') != plan.local.model_dump()
            or actual.get('visitante') != plan.visitante.model_dump()
            or instante(actual['fecha_hora']) != instante(plan.inicio)
            or actual.get('estadisticas_control') != control):
            raise ValueError('El partido cambió antes de escribir las muestras')
        desde = 0 if i == 0 else plan.deportivo.ticks[i - 1].reloj.minuto * 60 + 5
        filas = plan.muestras(desde, tick.reloj.minuto * 60)
        # Influx primero. Un fallo posterior se reintenta con las mismas claves y valores.
        influx_adapter.escribir_muestras(line_protocol(plan, filas))
        aplicar_tick(codigo, tick)
        doc = mongo_adapter.find_estadisticas(codigo)
        if doc.get('estadisticas_control') != control:
            raise ValueError('Otra ejecución avanzó el plan; detener y consultar')
        siguiente = plan.control(i)
        if not mongo_adapter.guardar_estadisticas(codigo, doc, {'estadisticas_control': siguiente}):
            raise ValueError('El partido cambió durante el avance; reintentar el mismo plan')
        control = siguiente
        print(json.dumps(dict(partido=codigo, tick=i + 1, muestras=control['muestras'], finalizado=tick.finalizado)), flush=True)
    resumen = consolidar(codigo)
    print(resumen.model_dump_json(indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archivo', type=Path, nargs='?')
    parser.add_argument('--crear-plan', metavar='CODIGO')
    parser.add_argument('--solo-validar', action='store_true')
    parser.add_argument('--modo', choices=['seed-final', 'vivo'], default='vivo')
    parser.add_argument('--intervalo', type=float, default=6)
    parser.add_argument('--consolidar', metavar='CODIGO', help='Recalcula únicamente el resumen final de equipos')
    args = parser.parse_args()
    if not math.isfinite(args.intervalo) or args.intervalo < 0:
        parser.error('El intervalo debe ser finito y no negativo')
    if args.consolidar:
        if args.archivo or args.crear_plan or args.solo_validar:
            parser.error('--consolidar se usa solo')
        # Valida el código sin conectar.
        from pydantic import TypeAdapter
        from typing import Annotated
        TypeAdapter(Annotated[str, Field(pattern=r'^P-[0-9]{3}$')]).validate_python(args.consolidar)
        print(consolidar(args.consolidar).model_dump_json(indent=2))
        return
    if not args.archivo:
        parser.error('Se requiere archivo de plan')
    if args.crear_plan:
        if args.archivo.exists():
            parser.error('El archivo ya existe; elegir otro nombre')
        deportivo = crear_plan(args.crear_plan)
        doc = mongo_adapter.find_estadisticas(deportivo.partido)
        plan = PlanEstadisticas(inicio=instante(doc['fecha_hora']).strftime('%Y-%m-%dT%H:%M:%SZ'),
            local=doc['local'], visitante=doc['visitante'], deportivo=deportivo)
        args.archivo.write_text(plan.model_dump_json(indent=2) + '\n')
        print(json.dumps(dict(archivo=str(args.archivo), partido=deportivo.partido, bases_modificadas=False)))
        return
    plan = PlanEstadisticas.model_validate_json(args.archivo.read_text())
    filas = plan.muestras(0, 5400)
    agregar_muestras(filas, plan.control(8), [plan.local.codigo, plan.visitante.codigo])
    if args.solo_validar:
        print(json.dumps(dict(partido=plan.deportivo.partido, ticks=9, muestras=len(filas),
            bases_modificadas=False, referencias_verificadas=False)))
        return
    ejecutar(plan, 0 if args.modo == 'seed-final' else args.intervalo)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Simulación detenida; se conservan los avances confirmados.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'Operación interrumpida: {type(exc).__name__}. Revisar plan, referencias y conexiones; '
              'reintentar el mismo plan conserva los avances.', file=sys.stderr)
        sys.exit(1)
    finally:
        mongo_adapter.close()
        influx_adapter.close()
