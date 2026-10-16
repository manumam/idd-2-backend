from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.equipos import EquipoRef


class SedeRef(BaseModel):
    codigo: str
    nombre: str
    ciudad: str


class JugadorRef(BaseModel):
    codigo: str
    nombre: str


class PartidoResponse(BaseModel):
    codigo: str
    fase: str
    grupo: Optional[str] = None
    fecha: date
    sede: Optional[SedeRef] = None
    local: Optional[EquipoRef] = None
    visitante: Optional[EquipoRef] = None


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
