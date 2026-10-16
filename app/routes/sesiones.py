from fastapi import APIRouter, Response

from app.schemas.errors import RESPUESTA_400, RESPUESTA_503, RESPUESTAS_FICHA
from app.schemas.params import SesionId
from app.schemas.sesiones import SesionResponse
from app.services import sesiones_service

router = APIRouter(tags=["Sesiones"])


@router.get(
    "/sesiones/{sesionId}",
    response_model=SesionResponse,
    summary="Consultar una sesión",
    description="No renueva la sesión. 404 si no existe o ya expiró.",
    responses=RESPUESTAS_FICHA,
)
def obtener_sesion(sesionId: SesionId) -> SesionResponse:
    return sesiones_service.obtener_sesion(sesionId)


@router.delete(
    "/sesiones/{sesionId}",
    status_code=204,
    response_class=Response,
    summary="Cerrar una sesión",
    description="Idempotente: responde 204 aunque la sesión ya no exista.",
    responses={**RESPUESTA_400, **RESPUESTA_503},
)
def cerrar_sesion(sesionId: SesionId) -> Response:
    sesiones_service.cerrar_sesion(sesionId)
    return Response(status_code=204)
