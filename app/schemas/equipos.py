from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class EquipoRef(BaseModel):
    codigo: str
    nombre: str


class EquipoResponse(BaseModel):
    codigo: str
    nombre: str
    confederacion: str
    grupo: str
    rankingFifa: int
    directorTecnico: Optional[str] = None
    anfitrion: bool


class JugadorResumen(BaseModel):
    codigo: str
    nombre: str
    apellido: str
    dorsal: int
    posicion: str
    equipo: EquipoRef


class JugadorDetalle(JugadorResumen):
    fechaNacimiento: date
    club: Optional[str] = None
    capitan: Optional[bool] = None


class JugadoresPagina(BaseModel):
    items: List[JugadorResumen]
    limit: int
    skip: int
