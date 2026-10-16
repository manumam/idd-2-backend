from fastapi import APIRouter

from app.schemas.errors import RESPUESTAS_FICHA
from app.schemas.params import CodigoPartido, CodigoSede, Confederacion, LimitEventos, LimitGoleadores
from app.schemas.partidos import EventosResponse, GoleadoresResponse, PartidoResponse
from app.services import partidos_service

router = APIRouter(tags=["Partidos y eventos"], responses=RESPUESTAS_FICHA)


@router.get("/partidos/{codigo}", response_model=PartidoResponse, summary="Ficha de un partido")
def obtener_partido(codigo: CodigoPartido) -> PartidoResponse:
    return partidos_service.obtener_partido(codigo)


@router.get(
    "/partidos/{codigo}/eventos",
    response_model=EventosResponse,
    summary="Eventos de un partido con sus protagonistas",
    description="Ordenados por minuto. Un partido sin eventos devuelve 200 con lista vacía.",
)
def listar_eventos(codigo: CodigoPartido, limit: LimitEventos = 50) -> EventosResponse:
    return partidos_service.listar_eventos(codigo, limit)


@router.get(
    "/sedes/{codigo}/goleadores",
    response_model=GoleadoresResponse,
    summary="Goles de jugadores de una confederación en una sede",
    description="Recorre sede, partidos, goles, autores y equipos. Sin goles devuelve 200 con lista vacía.",
)
def listar_goleadores(codigo: CodigoSede, confederacion: Confederacion, limit: LimitGoleadores = 50) -> GoleadoresResponse:
    return partidos_service.listar_goleadores(codigo, confederacion, limit)
