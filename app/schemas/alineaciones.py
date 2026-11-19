"""Instantáneas de la convocatoria por encuentro, independientes del plantel actual."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.equipos import EquipoRef


class JugadorAlineacion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    codigo: str = Field(pattern=r"^[A-Z]{3}-[1-9][0-9]?$")
    nombre: str = Field(min_length=1)
    dorsal: int = Field(ge=1, le=99)
    posicion: str = Field(min_length=1)


CodigoFormacion = Annotated[str, Field(pattern=r"^[A-Z]{3}-[1-9][0-9]?$")]
LineaFormacion = Annotated[list[CodigoFormacion], Field(min_length=1, max_length=5)]


class Formacion(BaseModel):
    """Disposición inicial; líneas desde defensa hacia ataque, sin tracking."""
    model_config = ConfigDict(extra="forbid", strict=True)
    arquero: str = Field(pattern=r"^[A-Z]{3}-[1-9][0-9]?$")
    lineas: list[LineaFormacion] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def diez_jugadores_de_campo(self):
        if any(not 1 <= len(linea) <= 5 for linea in self.lineas):
            raise ValueError("Cada línea debe contener de uno a cinco jugadores")
        codigos = [self.arquero] + [codigo for linea in self.lineas for codigo in linea]
        if len(codigos) != 11 or len(set(codigos)) != 11:
            raise ValueError("La formación debe ubicar once jugadores distintos")
        return self


class AlineacionEquipo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipo: EquipoRef
    titulares: list[JugadorAlineacion] = Field(min_length=11, max_length=11)
    suplentes: list[JugadorAlineacion] = Field(max_length=15)
    formacion: Formacion | None = None

    @model_validator(mode="after")
    def convocatoria_consistente(self):
        jugadores = self.titulares + self.suplentes
        if len({j.codigo for j in jugadores}) != len(jugadores):
            raise ValueError("Jugador repetido en la convocatoria")
        if len({j.dorsal for j in jugadores}) != len(jugadores):
            raise ValueError("Dorsal repetido en la convocatoria")
        if any(j.codigo.split("-")[0] != self.equipo.codigo for j in jugadores):
            raise ValueError("Jugador de otra selección")
        if self.formacion:
            ubicados = {self.formacion.arquero} | {c for linea in self.formacion.lineas for c in linea}
            if ubicados != {j.codigo for j in self.titulares}:
                raise ValueError("La formación debe incluir exactamente los titulares")
        return self


class Alineaciones(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local: AlineacionEquipo | None = None
    visitante: AlineacionEquipo | None = None

    @model_validator(mode="after")
    def selecciones_distintas(self):
        if self.local and self.visitante and self.local.equipo.codigo == self.visitante.equipo.codigo:
            raise ValueError("Las selecciones deben ser distintas")
        return self


class AlineacionesResponse(Alineaciones):
    partido: str = Field(pattern=r"^P-[0-9]{3}$")
