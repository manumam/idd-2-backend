from datetime import date
from typing import List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.equipos import EquipoRef
from app.schemas.fixture import PartidoFixture
from app.schemas.fixture import ResultadoFixture


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


class JugadorEvento(JugadorRef):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(pattern=r"^[A-Z]{3}-([1-9]|[1-9][0-9])$")
    nombre: str = Field(min_length=1)


class EquipoEvento(EquipoRef):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(pattern=r"^[A-Z]{3}$")
    nombre: str = Field(min_length=1)


class Protagonista(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jugador: JugadorEvento
    rol: Literal["autor", "asistente", "entra", "sale"]


class EventoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    tipo: Literal["gol", "autogol", "tarjeta_amarilla", "tarjeta_roja", "cambio"]
    minuto: int = Field(ge=0, le=120, strict=True)
    adicional: int = Field(default=0, ge=0, le=30, strict=True)
    equipo: EquipoEvento
    protagonistas: List[Protagonista] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def participantes_validos(self):
        roles = sorted(p.rol for p in self.protagonistas)
        permitidos = [["entra", "sale"]] if self.tipo == "cambio" else (
            [["autor"], ["asistente", "autor"]] if self.tipo == "gol" else [["autor"]])
        if roles not in permitidos:
            raise ValueError("Roles inválidos para el tipo de evento")
        codigos = [p.jugador.codigo for p in self.protagonistas]
        if len(set(codigos)) != len(codigos):
            raise ValueError("Un jugador no puede ocupar ambos roles")
        if any(not codigo.startswith(self.equipo.codigo + "-") for codigo in codigos):
            raise ValueError("Los jugadores deben pertenecer a la selección del evento")
        return self


class EventosResponse(BaseModel):
    partido: str
    items: List[EventoResponse]
    total: int
    siguiente_skip: int | None
    estado: Literal["proximo", "en_vivo", "finalizado"]
    resultado: ResultadoFixture | None
    reloj: RelojPartido | None
