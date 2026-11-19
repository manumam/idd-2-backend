from fastapi import APIRouter

from app.schemas.alineaciones import AlineacionesResponse
from app.schemas.errors import RESPUESTAS_FICHA, ErrorResponse
from app.schemas.params import CodigoPartido, LimitEventos, SkipEventos
from app.schemas.partidos import EventosResponse, PartidoResponse
from app.services import partidos_service

router = APIRouter(tags=["Partidos y eventos"], responses=RESPUESTAS_FICHA)


@router.get("/partidos/{codigo}", response_model=PartidoResponse, summary="Ficha de un partido",
            description="Detalle desde MongoDB con sede, fecha/hora UTC, estado, resultado y reloj persistido (puede ser null si aún no fue informado). Tanda separada de goles de juego. Plazas de playoffs resueltas como en el cuadro; requiere_revision identifica resultados obsoletos o no decisivos. Redis opcional con claves versionadas por las entradas actuales y TTL corto. fecha se conserva como fecha UTC por compatibilidad.")
def obtener_partido(codigo: CodigoPartido) -> PartidoResponse:
    return partidos_service.obtener_partido(codigo)


@router.get(
    "/partidos/{codigo}/eventos",
    response_model=EventosResponse,
    summary="Eventos de un partido con sus protagonistas",
    description="Cronología desde MongoDB con Redis opcional versionado. Orden por minuto, adicional y código; paginación limit/skip con total y siguiente_skip. Incluye equipo, protagonistas y una instantánea consistente del estado, resultado y reloj. Sin eventos: 200 vacío; partido inexistente: 404. No incluye tandas. Plazas obsoletas no heredan eventos.",
    responses={500: {"model": ErrorResponse, "description": "Eventos persistidos inválidos; requieren revisión"}},
)
def listar_eventos(codigo: CodigoPartido, limit: LimitEventos = 50, skip: SkipEventos = 0) -> EventosResponse:
    return partidos_service.listar_eventos(codigo, limit, skip)


@router.get(
    "/partidos/{codigo}/alineaciones",
    response_model=AlineacionesResponse,
    summary="Alineaciones de un partido",
    responses={500: {"model": ErrorResponse, "description": "Alineaciones persistidas inválidas; requieren revisión"}},
    description="Titulares y suplentes por selección, con código de jugador, nombre completo, dorsal y posición del encuentro. Incluye formacion opcional con arquero y lineas ordenadas desde defensa hacia ataque, de izquierda a derecha al mirar al arco rival. Contiene exactamente los once titulares; no es tracking en vivo. Cada lado es null si aún no fue informado o pertenece a una plaza obsoleta. Partido inexistente: 404. MongoDB con Redis opcional versionado; no reemplaza datos faltantes con el plantel.",
)
def obtener_alineaciones(codigo: CodigoPartido):
    return partidos_service.obtener_alineaciones(codigo)
