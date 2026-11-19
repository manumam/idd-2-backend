from datetime import date
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.equipos import EquipoRef
from app.schemas.fixture import PartidoFixture


class SedeRef(BaseModel):
    codigo: str
    nombre: str
    ciudad: str


class JugadorRef(BaseModel):
    codigo: str
    nombre: str


class RelojPartido(BaseModel):
    """Instantánea informada por la ingesta; nunca se infiere del horario."""
    model_config = ConfigDict(extra="forbid", strict=True)
    periodo: Literal["primer_tiempo", "entretiempo", "segundo_tiempo", "prorroga_primer_tiempo",
                     "descanso_prorroga", "prorroga_segundo_tiempo", "tanda", "pausa"]
    minuto: int = Field(ge=0, le=120)
    adicional: int = Field(default=0, ge=0)


class PartidoResponse(PartidoFixture):
    sede: Optional[SedeRef] = None
    reloj: RelojPartido | None = None
    origen_local: str | None = None
    origen_visitante: str | None = None
    requiere_revision: bool = False

    @computed_field
    @property
    def fecha(self) -> date:
        """Fecha UTC conservada por compatibilidad; usar fecha_hora para visualizar."""
        return self.fecha_hora.date()

    @model_validator(mode="after")
    def sin_reloj_antes_del_inicio(self):
        if self.estado == "proximo" and self.reloj is not None:
            raise ValueError("Un partido próximo no tiene reloj de juego")
        return self


class Protagonista(BaseModel):
    jugador: JugadorRef
    rol: str


class EventoResponse(BaseModel):
    codigo: str
    tipo: str
    minuto: int
    protagonistas: List[Protagonista]


class EventosResponse(BaseModel):
    partido: str
    items: List[EventoResponse]


class GolResponse(BaseModel):
    jugador: JugadorRef
    equipo: EquipoRef
    partido: str
    minuto: int


class GoleadoresResponse(BaseModel):
    sede: str
    confederacion: str
    items: List[GolResponse]
