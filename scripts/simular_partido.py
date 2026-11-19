#!/usr/bin/env python3
"""Reproduce un plan explícito de ticks sobre un partido existente; nunca reinicia datos."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.services.seguimiento_service import TickPartido, aplicar_tick


class PlanPartido(BaseModel):
    model_config = ConfigDict(extra="forbid")
    partido: str = Field(pattern=r"^P-[0-9]{3}$")
    ticks: list[TickPartido] = Field(min_length=1)

    @model_validator(mode="after")
    def secuencia_valida(self):
        ids = set()
        anterior = 0
        for i, tick in enumerate(self.ticks):
            if tick.reloj.minuto < anterior:
                raise ValueError("Los ticks deben avanzar por minuto")
            anterior = tick.reloj.minuto
            if tick.finalizado and i != len(self.ticks) - 1:
                raise ValueError("El cierre debe ser el último tick")
            if tick.finalizado and tick.reloj.minuto < 90:
                raise ValueError("El cierre requiere al menos 90 minutos")
            for evento in tick.eventos:
                if evento.codigo in ids:
                    raise ValueError("ID de evento repetido en el plan")
                ids.add(evento.codigo)
                if (evento.minuto, evento.adicional) > (tick.reloj.minuto, tick.reloj.adicional):
                    raise ValueError("Evento posterior al tick")
        return self


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archivo", type=Path, help="Plan JSON con partido y ticks; ver docs/eventos.md")
    parser.add_argument("--crear-plan", metavar="CODIGO", help="Genera el archivo usando equipos y jugadores existentes, sin escribir en las bases")
    parser.add_argument("--intervalo", type=float, default=5, help="Segundos entre ticks (mínimo 0)")
    parser.add_argument("--solo-validar", action="store_true", help="Valida estructura sin conectar ni escribir")
    args = parser.parse_args()
    if args.intervalo < 0 or not math.isfinite(args.intervalo):
        parser.error("El intervalo debe ser finito y no negativo")
    if args.crear_plan:
        if args.archivo.exists():
            parser.error("El archivo de salida ya existe; elegir otro nombre")
        plan = crear_plan(args.crear_plan)
        args.archivo.write_text(plan.model_dump_json(indent=2) + "\n")
        print(json.dumps({"archivo": str(args.archivo), "partido": plan.partido, "ticks": len(plan.ticks), "bases_modificadas": False}))
        return
    plan = PlanPartido.model_validate_json(args.archivo.read_text())
    if args.solo_validar:
        print(json.dumps({"partido": plan.partido, "ticks": len(plan.ticks), "referencias_verificadas": False}))
        return
    from app.adapters import mongo_adapter
    try:
        # El esquema existente puede prohibir eventos; actualizarlo solo al ejecutar explícitamente.
        validator = json.loads((ROOT / "data/fixture/partidos-validator.json").read_text())
        mongo_adapter.db.command("collMod", "partidos", validator=validator,
                                 validationLevel="strict", validationAction="error")
        for i, tick in enumerate(plan.ticks):
            if i:
                time.sleep(args.intervalo)
            aplicado = aplicar_tick(plan.partido, tick)
            print(json.dumps({"partido": plan.partido, "tick": i + 1,
                              "aplicado": aplicado, "finalizado": tick.finalizado}), flush=True)
    finally:
        mongo_adapter.close()


def jugadores_de_campo(plantel: list[dict]) -> list[dict]:
    """Prioriza atacantes; desempata desde el dorsal más alto, nunca por el arquero."""
    prioridad = {"delantero": 0, "mediocampista": 1, "defensor": 2}
    return sorted((j for j in plantel if j.get("posicion", "").strip().casefold() in prioridad),
        key=lambda j: (prioridad[j["posicion"].strip().casefold()], -j["dorsal"], j["_id"]))


def participantes_demo(plantel: list[dict], alineacion, con_cambio: bool) -> list[dict]:
    """Si hay convocatoria, el autor inicial es titular y quien entra es suplente."""
    candidatos = jugadores_de_campo(plantel)
    if alineacion is None:
        if len(candidatos) < (2 if con_cambio else 1):
            raise ValueError("Faltan jugadores de campo para el guion")
        return candidatos[:2] if con_cambio else candidatos[:1]
    titulares = {j.codigo for j in alineacion.titulares if j.posicion.strip().casefold() != "arquero"}
    suplentes = {j.codigo for j in alineacion.suplentes if j.posicion.strip().casefold() != "arquero"}
    if alineacion.formacion:
        titulares.discard(alineacion.formacion.arquero)
    iniciales = [j for j in candidatos if j["_id"] in titulares]
    reservas = [j for j in candidatos if j["_id"] in suplentes]
    if not iniciales or (con_cambio and not reservas):
        raise ValueError("La convocatoria necesita un titular y un suplente de campo para el guion")
    return [iniciales[0], reservas[0]] if con_cambio else [iniciales[0]]


def crear_plan(codigo: str) -> PlanPartido:
    """Guion corto de demo con referencias reales; no carga catálogos ni inventa jugadores."""
    from app.adapters import mongo_adapter
    from app.schemas.partidos import PartidoResponse
    from app.schemas.alineaciones import Alineaciones
    # Validar el código antes de conectar.
    PlanPartido(partido=codigo, ticks=[TickPartido(reloj={"periodo": "primer_tiempo", "minuto": 0})])
    try:
        documento = mongo_adapter.find_eventos(codigo)
        if documento is None:
            raise ValueError("Partido inexistente")
        partido = PartidoResponse.model_validate(dict(codigo=codigo, **{
            k: v for k, v in documento.items() if k not in ("_id", "eventos", "actualizado_en")}))
        if partido.estado != "proximo" or not partido.local or not partido.visitante:
            raise ValueError("Elegir un partido próximo con ambas selecciones definidas")
        equipos = [partido.local, partido.visitante]
        planteles = [mongo_adapter.list_jugadores(e.codigo, None, 100, 0) for e in equipos]
        convocatoria = mongo_adapter.find_alineaciones(codigo)
        alineaciones = Alineaciones.model_validate((convocatoria or {}).get("alineaciones") or {})
        elegidos = []
        for i, lado in enumerate(("local", "visitante")):
            alineacion = getattr(alineaciones, lado)
            if alineacion and alineacion.equipo.codigo != equipos[i].codigo:
                raise ValueError("La convocatoria no corresponde a la selección del encuentro")
            elegidos.append(participantes_demo(planteles[i], alineacion, con_cambio=i == 0))
        def evento(tipo, minuto, lado, protagonistas):
            return dict(codigo=f"{codigo}-{minuto}-{tipo}", tipo=tipo, minuto=minuto,
                equipo=equipos[lado].model_dump(), protagonistas=[dict(rol=rol, jugador=dict(
                    codigo=elegidos[lado][indice]["_id"],
                    nombre=f'{elegidos[lado][indice]["nombre"]} {elegidos[lado][indice].get("apellido", "")}'.strip()))
                    for rol, indice in protagonistas])
        ticks = []
        for minuto, periodo, eventos, finalizado in [
            (0, "primer_tiempo", [], False),
            (12, "primer_tiempo", [evento("gol", 12, 0, [("autor", 0)])], False),
            (28, "primer_tiempo", [evento("tarjeta_amarilla", 28, 1, [("autor", 0)])], False),
            (45, "entretiempo", [], False),
            (46, "segundo_tiempo", [], False),
            (62, "segundo_tiempo", [evento("cambio", 62, 0, [("sale", 0), ("entra", 1)])], False),
            (78, "segundo_tiempo", [evento("gol", 78, 0, [("autor", 1)])], False),
            (82, "segundo_tiempo", [evento("tarjeta_roja", 82, 1, [("autor", 0)])], False),
            (90, "segundo_tiempo", [], True),
        ]:
            ticks.append(dict(reloj=dict(periodo=periodo, minuto=minuto), eventos=eventos, finalizado=finalizado))
        return PlanPartido(partido=codigo, ticks=ticks)
    finally:
        mongo_adapter.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Simulación detenida; se conservan los ticks confirmados.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Simulación interrumpida: {type(exc).__name__}. Revisar plan, referencias y conectividad; "
              "se conservan los ticks confirmados.", file=sys.stderr)
        sys.exit(1)
