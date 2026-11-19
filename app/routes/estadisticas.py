from typing import Optional

from fastapi import APIRouter

from app.schemas.errors import RESPUESTA_400, RESPUESTA_503
from app.schemas.comparacion import ComparacionResponse
from app.core.exceptions import InvalidRequestError
from app.services.comparacion_service import obtener_comparacion
from app.schemas.estadisticas import EstadisticasResponse
from app.schemas.params import CodigoPartido, EquipoQuery, FechaHora, Ventana
from app.services import estadisticas_service

router = APIRouter(tags=["Estadísticas"])


@router.get(
    "/partidos/{codigo}/estadisticas",
    response_model=ComparacionResponse | EstadisticasResponse,
    summary="Comparación de equipos o serie temporal por intervalo",
    description=(
        "Sin fechas devuelve la comparación de ambos equipos, provisional o final consolidada. "
        "Con desde y hasta devuelve la serie temporal histórica. equipo y ventana requieren ambas fechas. "
        "Puntos cada 5 segundos por equipo en [`desde`, `hasta`). Sin `ventana`, el intervalo máximo es de 30 "
        "minutos; con `ventana` (`1m` o `5m`) es de 2 horas y cada medida se agrega según su tipo "
        "(promedio de posesión, máximo de tiros, suma de pases). Un intervalo sin puntos o un partido "
        "sin datos devuelve 200 con lista vacía."
    ),
    responses={**RESPUESTA_400, **RESPUESTA_503, 404: {"description": "Partido no encontrado en la consulta de comparación"}},
)
def obtener_estadisticas(
    codigo: CodigoPartido,
    desde: Optional[FechaHora] = None,
    hasta: Optional[FechaHora] = None,
    equipo: Optional[EquipoQuery] = None,
    ventana: Optional[Ventana] = None,
) -> ComparacionResponse | EstadisticasResponse:
    if desde is None and hasta is None:
        if equipo is not None or ventana is not None:
            raise InvalidRequestError("equipo y ventana requieren desde y hasta.")
        return obtener_comparacion(codigo)
    if desde is None or hasta is None:
        raise InvalidRequestError("Informar desde y hasta juntos.")
    return estadisticas_service.obtener_estadisticas(codigo, desde, hasta, equipo, ventana)
