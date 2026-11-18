"""Cuadro de la demo: orígenes persistentes y resolución derivada."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.equipos import EquipoRef
from app.schemas.fixture import PartidoFixture


class Modelo(BaseModel):
    model_config = ConfigDict(extra='forbid')


class OrigenGrupo(Modelo):
    tipo: Literal['grupo']
    grupo: str = Field(pattern=r'^[A-P]$')
    posicion: int = Field(ge=1, le=2, strict=True)


class OrigenGanador(Modelo):
    tipo: Literal['ganador']
    cruce: str = Field(pattern=r'^P-[0-9]{3}$')


class OrigenEquipo(Modelo):
    tipo: Literal['equipo']
    equipo: EquipoRef


Origen = Annotated[OrigenGrupo | OrigenGanador | OrigenEquipo, Field(discriminator='tipo')]


class Cruce(Modelo):
    codigo: str = Field(pattern=r'^P-[0-9]{3}$')
    fase: Literal['Dieciseisavos', 'Octavos', 'Cuartos', 'Semifinal', 'Final']
    orden: int = Field(ge=1, strict=True)
    local: Origen
    visitante: Origen


class Plaza(Modelo):
    origen: Origen
    descripcion: str
    equipo: EquipoRef | None


class CruceResuelto(Modelo):
    codigo: str
    fase: str
    orden: int
    local: Plaza
    visitante: Plaza
    partido: PartidoFixture
    ganador: EquipoRef | None
    siguiente: str | None
    requiere_revision: bool


class PlayoffsResponse(Modelo):
    items: list[CruceResuelto]
