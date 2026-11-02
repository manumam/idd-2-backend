"""Contrato de lectura del feed del Hito 6."""

from typing import Optional
from pydantic import BaseModel


class Comentario(BaseModel):
    comentarioId: str
    usuarioId: str
    nombreUsuario: str
    idioma: str
    texto: str
    estadoModeracion: str


class ComentariosPagina(BaseModel):
    partido: str
    bloque: str
    items: list[Comentario]
    siguienteCursor: Optional[str]
