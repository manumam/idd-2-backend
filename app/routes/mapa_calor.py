from typing import Optional

from fastapi import APIRouter

from app.schemas.errors import RESPUESTAS_FICHA
from app.schemas.mapa_calor import MapaCalorResponse
from app.schemas.params import CodigoPartido, JugadorQuery, MinutoQuery
from app.services import mapa_calor_service

router = APIRouter(tags=["Mapa de calor"])


@router.get(
    "/partidos/{codigo}/mapa-calor",
    response_model=MapaCalorResponse,
    summary="Mapa de calor de un jugador en un partido",
    description=(
        "Muestras de posición por celda de 5 × 5 m (cancha de 105 × 68 m, 21 × 14 celdas), contadas en InfluxDB, "
        "con intensidad relativa a la celda más ocupada; las celdas sin muestras se omiten. Los minutos se "
        "cuentan desde el inicio del tracking del partido, con inicio inclusivo y fin exclusivo, entre 0 y 120. "
        "Sin `desde_minuto` empieza en 0; sin `hasta_minuto`, llega al minuto transcurrido del reloj "
        "(120 si no hay reloj). En vivo lee el tracking crudo (`fuente: en_vivo`); finalizado, la ocupación "
        "materializada por minuto (`fuente: historico`), o el crudo si todavía no se materializó. "
        "Partido próximo: 200 con `celdas` vacía, `fuente` e `intervalo` null. "
        "Partido inexistente o jugador ajeno a sus selecciones: 404."
    ),
    responses=RESPUESTAS_FICHA,
)
def obtener_mapa_calor(
    codigo: CodigoPartido,
    jugador_id: JugadorQuery,
    desde_minuto: Optional[MinutoQuery] = None,
    hasta_minuto: Optional[MinutoQuery] = None,
) -> MapaCalorResponse:
    return mapa_calor_service.obtener_mapa_calor(codigo, jugador_id, desde_minuto, hasta_minuto)
