from typing import Optional

from pydantic import BaseModel


class SesionResponse(BaseModel):
    sesionId: str
    usuarioId: Optional[str] = None
    nombreUsuario: Optional[str] = None
    rol: Optional[str] = None
    idioma: Optional[str] = None
    ultimoAcceso: Optional[str] = None
    acciones: Optional[int] = None
    ttlSegundos: Optional[int] = None
