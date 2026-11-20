"""Pedido y estado de la simulación en vivo lanzada desde la demo."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SimulacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    partido: str | None = Field(default=None, pattern=r"^P-[0-9]{3}$", examples=["P-001"])
    factor: float = Field(default=10, ge=1, le=120, description="Segundos de juego por segundo real")


class SimulacionEstado(BaseModel):
    en_curso: bool
    partido: str | None = Field(examples=["P-001"])
    factor: float | None = Field(examples=[10])
    segundo_de_juego: int | None = Field(description="Último segundo de juego confirmado por un tick del guion",
                                         examples=[2700])
    iniciada_en: datetime | None = Field(examples=["2026-11-20T18:30:00Z"])
    finalizada: bool
    error: str | None = None
    siguiente: str | None = Field(examples=["P-004"])
