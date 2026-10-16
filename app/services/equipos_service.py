"""Casos de uso 1 a 3: equipos y jugadores (MongoDB)."""

from typing import Any, Dict, Optional

from app.adapters import mongo_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.equipos import (
    EquipoRef,
    EquipoResponse,
    JugadorDetalle,
    JugadoresPagina,
    JugadorResumen,
)


def _resumen(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "codigo": doc["_id"],
        "nombre": doc["nombre"],
        "apellido": doc["apellido"],
        "dorsal": doc["dorsal"],
        "posicion": doc["posicion"],
        "equipo": EquipoRef(codigo=doc["equipo"]["_id"], nombre=doc["equipo"]["nombre"]),
    }


def obtener_equipo(codigo: str) -> EquipoResponse:
    doc = mongo_adapter.find_equipo(codigo)
    if doc is None:
        raise ResourceNotFoundError("EQUIPO_NO_ENCONTRADO", f"No existe el equipo '{codigo}'.")
    return EquipoResponse(
        codigo=doc["_id"],
        nombre=doc["nombre"],
        confederacion=doc["confederacion"],
        grupo=doc["grupo"],
        rankingFifa=doc["ranking_fifa"],
        directorTecnico=doc.get("director_tecnico"),
        anfitrion=doc["anfitrion"],
    )


def obtener_jugador(codigo: str) -> JugadorDetalle:
    doc = mongo_adapter.find_jugador(codigo)
    if doc is None:
        raise ResourceNotFoundError("JUGADOR_NO_ENCONTRADO", f"No existe el jugador '{codigo}'.")
    return JugadorDetalle(
        **_resumen(doc),
        fechaNacimiento=doc["fecha_nacimiento"].date(),
        club=doc.get("club"),
        capitan=doc.get("capitan"),
    )


def listar_jugadores(equipo: str, posicion: Optional[str], limit: int, skip: int) -> JugadoresPagina:
    docs = mongo_adapter.list_jugadores(equipo, posicion, limit, skip)
    return JugadoresPagina(items=[JugadorResumen(**_resumen(d)) for d in docs], limit=limit, skip=skip)
