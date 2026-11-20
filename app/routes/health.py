from fastapi import APIRouter, Response

from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["Sistema"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado de las dependencias",
    description="Consulta en paralelo MongoDB, Redis e InfluxDB. Responde 200 aunque una fuente esté caída: la marca como `down`. "
                "Reusa el último ping de cada fuente durante 15 s: el estado puede tener hasta 15 s de atraso.",
)
def health() -> HealthResponse:
    return HealthResponse(estado=health_service.estado_dependencias())


@router.get('/live', response_model=LivenessResponse, summary='Proceso de la API activo',
            description='No consulta dependencias ni verifica datos de dominio.')
def live() -> LivenessResponse:
    return LivenessResponse()


@router.get('/ready', response_model=ReadinessResponse, summary='Readiness de conectividad',
            description='200 si pasa el ping de MongoDB; 503 si falla. Redis es caché opcional y no se evalúa. InfluxDB tampoco: '
                        'si cae, solo las rutas que lo usan responden 503 `INFLUXDB_UNAVAILABLE` y su estado se informa en `/health`. '
                        'Reusa el último ping de cada fuente durante 15 s: el estado puede tener hasta 15 s de atraso. No certifica datos de dominio.',
            responses={503: {'model': ReadinessResponse, 'description': 'MongoDB no está disponible'}})
def ready(response: Response) -> ReadinessResponse:
    estados, listo = health_service.estado_readiness()
    response.status_code = 200 if listo else 503
    return ReadinessResponse(estado=estados, listo=listo)
