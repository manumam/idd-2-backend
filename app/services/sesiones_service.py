"""Casos de uso 9 y 10: consulta y cierre de sesiones (Redis)."""

from app.adapters import redis_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.sesiones import SesionResponse


def obtener_sesion(sesion_id: str) -> SesionResponse:
    sesion = redis_adapter.get_sesion(sesion_id)
    if sesion is None:
        raise ResourceNotFoundError("SESION_NO_VIGENTE", f"No existe una sesión vigente '{sesion_id}'.")
    campos = sesion["campos"]
    acciones = campos.get("acciones")
    ttl = sesion["ttl"]
    return SesionResponse(
        sesionId=sesion_id,
        usuarioId=campos.get("usuario_id"),
        nombreUsuario=campos.get("nombre_usuario"),
        rol=campos.get("rol"),
        idioma=campos.get("idioma"),
        ultimoAcceso=campos.get("ultimo_acceso"),
        acciones=int(acciones) if acciones is not None else None,
        ttlSegundos=ttl if ttl >= 0 else None,  # -1: la clave no tiene vencimiento
    )


def cerrar_sesion(sesion_id: str) -> None:
    redis_adapter.delete_sesion(sesion_id)
