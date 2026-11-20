from fastapi import APIRouter

from app.schemas.errors import RESPUESTA_400, RESPUESTA_404, RESPUESTA_503, ErrorResponse
from app.schemas.simulacion import SimulacionEstado, SimulacionRequest
from app.services import simulacion_demo_service

router = APIRouter(tags=["Demo"])


@router.get("/demo/simulacion", response_model=SimulacionEstado, summary="Estado de la simulación en vivo",
            description="Última simulación lanzada por este proceso de la API, o la que está en curso. No consulta bases. segundo_de_juego avanza con cada tick confirmado del guion.")
def estado_simulacion() -> SimulacionEstado:
    return simulacion_demo_service.estado_simulacion()


@router.post(
    "/demo/simulacion",
    response_model=SimulacionEstado,
    status_code=202,
    summary="Simular un partido en vivo",
    description="Lanza scripts/simular_en_vivo.py como proceso aparte para un partido próximo con alineaciones, sin simulaciones previas, y responde sin esperar a que termine. Modifica eventos, reloj, marcador y estado del partido hasta finalizarlo y escribe en InfluxDB; no es reanudable. Deshabilitada salvo DEMO_SIMULACION_HABILITADA=true. Una simulación a la vez por proceso de la API.",
    responses={
        **RESPUESTA_400,
        403: {"model": ErrorResponse, "description": "Demo deshabilitada (DEMO_DESHABILITADA)"},
        **RESPUESTA_404,
        409: {"model": ErrorResponse, "description": "SIMULACION_EN_CURSO o PARTIDO_NO_SIMULABLE"},
        **RESPUESTA_503,
    },
)
def iniciar_simulacion(pedido: SimulacionRequest) -> SimulacionEstado:
    return simulacion_demo_service.iniciar_simulacion(pedido.partido, pedido.factor)
