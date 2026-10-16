from fastapi import APIRouter

from app.schemas.health import HealthResponse
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
