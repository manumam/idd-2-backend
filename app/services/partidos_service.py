"""Casos de uso 4 a 6: partidos, eventos y goleadores por sede (Neo4j)."""

from app.adapters import neo4j_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.equipos import EquipoRef
from app.schemas.partidos import (
    EventoResponse,
    EventosResponse,
    GoleadoresResponse,
    GolResponse,
    JugadorRef,
    PartidoResponse,
    Protagonista,
    SedeRef,
)


def _partido_no_encontrado(codigo: str) -> ResourceNotFoundError:
    return ResourceNotFoundError("PARTIDO_NO_ENCONTRADO", f"No existe el partido '{codigo}'.")


def _equipo(codigo, nombre):
    return EquipoRef(codigo=codigo, nombre=nombre) if codigo is not None else None


def obtener_partido(codigo: str) -> PartidoResponse:
    p = neo4j_adapter.find_partido(codigo)
    if p is None:
        raise _partido_no_encontrado(codigo)
    sede = p["sede"]
    local = p.get("local")
    visitante = p.get("visitante")
    return PartidoResponse(
        codigo=p["id"],
        fase=p["fase"],
        grupo=p["grupo"] or None,  # sin grupo fuera de la fase de grupos
        fecha=p["fecha"],
        sede=SedeRef(codigo=sede["id"], nombre=sede["nombre"], ciudad=sede["ciudad"]) if sede else None,
        local=_equipo(local["id"], local["nombre"]) if local else None,
        visitante=_equipo(visitante["id"], visitante["nombre"]) if visitante else None,
    )


def listar_eventos(codigo: str, limit: int) -> EventosResponse:
    eventos = neo4j_adapter.find_eventos(codigo, limit)
    if eventos is None:
        raise _partido_no_encontrado(codigo)
    items = [
        EventoResponse(
            codigo=e["id"],
            tipo=e["tipo"],
            minuto=e["minuto"],
            protagonistas=[
                Protagonista(jugador=JugadorRef(codigo=j["id"], nombre=j["nombre"]), rol=j["rol"])
                for j in e["protagonistas"]
            ],
        )
        for e in eventos
    ]
    return EventosResponse(partido=codigo, items=items)


def listar_goleadores(sede: str, confederacion: str, limit: int) -> GoleadoresResponse:
    if not neo4j_adapter.sede_existe(sede):
        raise ResourceNotFoundError("SEDE_NO_ENCONTRADA", f"No existe la sede '{sede}'.")
    goles = neo4j_adapter.find_goleadores(sede, confederacion, limit)
    items = [
        GolResponse(
            jugador=JugadorRef(codigo=g["jugador_id"], nombre=g["jugador_nombre"]),
            equipo=EquipoRef(codigo=g["equipo_id"], nombre=g["equipo_nombre"]),
            partido=g["partido"],
            minuto=g["minuto"],
        )
        for g in goles
    ]
    return GoleadoresResponse(sede=sede, confederacion=confederacion, items=items)
