from typing import Optional

from fastapi import APIRouter

from app.schemas.equipos import EquipoResponse, EquiposResponse, JugadorDetalle, JugadoresPagina
from app.schemas.errors import RESPUESTAS_FICHA, RESPUESTAS_LISTA
from app.schemas.params import CodigoEquipo, CodigoJugador, EquipoQuery, Limit, Posicion, Skip
from app.services import equipos_service

router = APIRouter(tags=["Equipos y jugadores"])


@router.get(
    "/equipos",
    response_model=EquiposResponse,
    summary="Catálogo de equipos",
    responses=RESPUESTAS_LISTA,
    description="Todos los equipos de MongoDB, ordenados por nombre y código. Sin filtros ni paginación; vacío permitido.",
)
def listar_equipos() -> EquiposResponse:
    return equipos_service.listar_equipos()


@router.get(
    "/equipos/{codigo}",
    response_model=EquipoResponse,
    summary="Ficha de un equipo",
    responses=RESPUESTAS_FICHA,
)
def obtener_equipo(codigo: CodigoEquipo) -> EquipoResponse:
    return equipos_service.obtener_equipo(codigo)


@router.get(
    "/jugadores",
    response_model=JugadoresPagina,
    summary="Plantel de un equipo",
    responses=RESPUESTAS_LISTA,
    description="Ordenado por dorsal. Un filtro sin resultados devuelve 200 con lista vacía.",
)
def listar_jugadores(
    equipo: EquipoQuery,
    posicion: Optional[Posicion] = None,
    limit: Limit = 20,
    skip: Skip = 0,
) -> JugadoresPagina:
    return equipos_service.listar_jugadores(equipo, posicion, limit, skip)


@router.get(
    "/jugadores/{codigo}",
    response_model=JugadorDetalle,
    summary="Ficha de un jugador",
    responses=RESPUESTAS_FICHA,
)
def obtener_jugador(codigo: CodigoJugador) -> JugadorDetalle:
    return equipos_service.obtener_jugador(codigo)
