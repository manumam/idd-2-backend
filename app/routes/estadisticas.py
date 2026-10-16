from typing import Optional

from fastapi import APIRouter

from app.schemas.errors import RESPUESTA_400, RESPUESTA_503
from app.schemas.estadisticas import EstadisticasResponse
from app.schemas.params import CodigoPartido, EquipoQuery, FechaHora, Ventana
from app.services import estadisticas_service

router = APIRouter(tags=["Estadísticas"])


@router.get(
    "/partidos/{codigo}/estadisticas",
    response_model=EstadisticasResponse,
    summary="Estadísticas de un partido en un intervalo",
    description=(
        "Puntos cada 5 segundos por equipo en [`desde`, `hasta`). Sin `ventana`, el intervalo máximo es de 30 "
        "minutos; con `ventana` (`1m` o `5m`) es de 2 horas y cada medida se agrega según su tipo "
        "(promedio de posesión, máximo de tiros, suma de pases). Un intervalo sin puntos o un partido "
        "sin datos devuelve 200 con lista vacía."
    ),
    responses={**RESPUESTA_400, **RESPUESTA_503},
)
def obtener_estadisticas(
    codigo: CodigoPartido,
    desde: FechaHora,
    hasta: FechaHora,
    equipo: Optional[EquipoQuery] = None,
    ventana: Optional[Ventana] = None,
) -> EstadisticasResponse:
    return estadisticas_service.obtener_estadisticas(codigo, desde, hasta, equipo, ventana)
