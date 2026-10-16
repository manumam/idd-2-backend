"""Formato de error único de la API."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["EQUIPO_NO_ENCONTRADO"])
    message: str = Field(examples=["No existe el equipo solicitado."])
    requestId: str = Field(examples=["3f6c2a9e-8d1b-4b7a-9c55-0e1f2a3b4c5d"])
