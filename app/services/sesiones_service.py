"""Casos de uso 9 y 10: consulta y cierre de sesiones (Redis)."""

from app.adapters import redis_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.sesiones import SesionResponse


def obtener_sesion(sesion_id: str) -> SesionResponse:
    sesion = redis_adapter.get_sesion(sesion_id)
    if sesion is None:
        raise ResourceNotFoundError("SESION_NO_VIGENTE", f"No existe una sesión vigente '{sesion_id}'.")
    return SesionResponse(
        sesionId=sesion_id,
        usuarioId=sesion["usuario_id"],
        nombreUsuario=sesion["nombre_usuario"],
        rol=sesion["rol"],
        idioma=sesion["idioma"],
        ultimoAcceso=sesion["ultimo_acceso"],
        acciones=sesion["acciones"],
        ttlSegundos=sesion["ttl_segundos"],
    )


def cerrar_sesion(sesion_id: str) -> None:
    redis_adapter.delete_sesion(sesion_id)
