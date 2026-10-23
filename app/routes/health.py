from fastapi import APIRouter, Response

from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["Sistema"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado de las dependencias",
    description="Responde 200 aunque una fuente esté caída: la marca como `down`.",
)
def health() -> HealthResponse:
    return HealthResponse(estado=health_service.estado_dependencias())


@router.get('/live', response_model=LivenessResponse, summary='Proceso de la API activo',
            description='No consulta dependencias ni verifica datos de dominio.')
def live() -> LivenessResponse:
    return LivenessResponse()


@router.get('/ready', response_model=ReadinessResponse, summary='Readiness de conectividad',
            description='200 si pasan los pings de las cuatro dependencias requeridas; 503 si alguna falla. No certifica datos de dominio.',
            responses={503: {'model': ReadinessResponse, 'description': 'Una o más dependencias no están disponibles'}})
def ready(response: Response) -> ReadinessResponse:
    estados = health_service.estado_dependencias()
    listo = all(estado == 'up' for estado in estados.values())
    response.status_code = 200 if listo else 503
    return ReadinessResponse(estado=estados, listo=listo)
