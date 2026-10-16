"""Formato de error único de la API."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["EQUIPO_NO_ENCONTRADO"])
    message: str = Field(examples=["No existe el equipo solicitado."])
    requestId: str = Field(examples=["3f6c2a9e-8d1b-4b7a-9c55-0e1f2a3b4c5d"])


# Respuestas de error para la documentación de rutas de lectura
RESPUESTA_400 = {400: {"model": ErrorResponse, "description": "Parámetro inválido"}}
RESPUESTA_404 = {404: {"model": ErrorResponse, "description": "Recurso inexistente"}}
RESPUESTA_503 = {503: {"model": ErrorResponse, "description": "Fuente de datos no disponible"}}

RESPUESTAS_FICHA = {**RESPUESTA_400, **RESPUESTA_404, **RESPUESTA_503}
RESPUESTAS_LISTA = {**RESPUESTA_400, **RESPUESTA_503}
