"""Contrato de comparación por equipo, separado de la serie temporal histórica."""
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.equipos import EquipoRef
from app.schemas.partidos import RelojPartido


class EstadisticasEquipo(BaseModel):
    equipo: EquipoRef
    posesion_pct: float | None = Field(default=None, ge=0, le=100)
    tiros: int | None = Field(default=None, ge=0)
    pases: int | None = Field(default=None, ge=0)
    goles: int | None = Field(default=None, ge=0)
    tarjetas_amarillas: int | None = Field(default=None, ge=0)
    tarjetas_rojas: int | None = Field(default=None, ge=0)


class ComparacionResponse(BaseModel):
    partido: str
    estado: Literal['proximo', 'en_vivo', 'finalizado']
    consolidacion: Literal['sin_datos', 'provisional', 'pendiente', 'completa']
    actualizado_en: str | None = None
    reloj: RelojPartido | None = None
    local: EstadisticasEquipo | None = None
    visitante: EstadisticasEquipo | None = None
    advertencias: list[str] = Field(default_factory=list)
