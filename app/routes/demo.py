from fastapi import APIRouter

from app.schemas.errors import RESPUESTA_400, RESPUESTA_404, RESPUESTA_503, ErrorResponse
from app.schemas.simulacion import SimulacionEstado, SimulacionRequest
from app.services import simulacion_demo_service

router = APIRouter(tags=["Demo"])


@router.get("/demo/simulacion", response_model=SimulacionEstado, summary="Estado de la simulación en vivo",
            description="Última simulación lanzada por este proceso de la API, o la que está en curso, y el próximo partido simulable. segundo_de_juego avanza con cada tick confirmado del guion.")
def estado_simulacion() -> SimulacionEstado:
    return simulacion_demo_service.estado_simulacion()


@router.post(
    "/demo/simulacion",
    response_model=SimulacionEstado,
    status_code=202,
    summary="Simular un partido en vivo",
    description="Lanza scripts/simular_en_vivo.py como proceso aparte. Sin partido elige el próximo partido simulable; con partido valida ese código. Requiere un partido próximo, sin datos previos y con las dos alineaciones. Responde sin esperar a que termine. Modifica eventos, reloj, marcador y estado hasta finalizarlo y escribe en InfluxDB; no es reanudable. Una simulación a la vez por proceso de la API.",
    responses={
        **RESPUESTA_400,
        **RESPUESTA_404,
        409: {"model": ErrorResponse, "description": "SIMULACION_EN_CURSO, SIN_PARTIDOS_SIMULABLES o PARTIDO_NO_SIMULABLE"},
        **RESPUESTA_503,
    },
)
def iniciar_simulacion(pedido: SimulacionRequest | None = None) -> SimulacionEstado:
    pedido = pedido or SimulacionRequest()
    return simulacion_demo_service.iniciar_simulacion(pedido.partido, pedido.factor)
