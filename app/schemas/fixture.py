"""Contrato de lectura del fixture del Mundial 2030."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.equipos import EquipoRef


class Marcador(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    goles_local: int = Field(ge=0)
    goles_visitante: int = Field(ge=0)


class ResultadoFixture(Marcador):
    penales: Marcador | None = None


class PartidoFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(pattern=r"^P-[0-9]{3}$")
    fecha_hora: datetime
    fase: str = Field(min_length=1)
    grupo: str | None = Field(default=None, pattern=r"^[A-P]$")
    local: EquipoRef | None
    visitante: EquipoRef | None
    estado: Literal["proximo", "en_vivo", "finalizado"]
    resultado: ResultadoFixture | None

    @field_validator("fecha_hora")
    @classmethod
    def fecha_utc(cls, value: datetime) -> datetime:
        # PyMongo devuelve BSON Date en UTC sin tzinfo por defecto.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def estado_y_resultado(self):
        if (self.estado == "proximo") != (self.resultado is None):
            raise ValueError("El marcador debe existir únicamente en vivo o finalizado")
        return self


class FixtureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PartidoFixture]
