"""Reglas explícitas de la demo y tabla derivada de resultados finalizados."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.equipos import EquipoRef
from app.schemas.fixture import PartidoFixture


class ReglasGrupo(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    victoria: int = Field(ge=0)
    empate: int = Field(ge=0)
    derrota: int = Field(ge=0)
    orden_desempate: list[str] = Field(min_length=2)


class Grupo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codigo: str = Field(pattern=r'^[A-P]$')
    equipos: list[EquipoRef] = Field(min_length=2)
    reglas: ReglasGrupo

    @model_validator(mode='after')
    def validar_participantes(self):
        codes = [e.codigo for e in self.equipos]
        orden = self.reglas.orden_desempate
        if len(set(codes)) != len(codes) or len(orden) != len(codes) or set(orden) != set(codes):
            raise ValueError('El desempate debe enumerar cada participante una sola vez')
        return self


class GruposResponse(BaseModel):
    items: list[Grupo]


class PosicionGrupo(BaseModel):
    posicion: int
    equipo: EquipoRef
    jugados: int = 0
    ganados: int = 0
    empatados: int = 0
    perdidos: int = 0
    goles_favor: int = 0
    goles_contra: int = 0
    diferencia_gol: int = 0
    puntos: int = 0


class PosicionesResponse(BaseModel):
    grupo: Grupo
    completa: bool
    items: list[PosicionGrupo]
    partidos: list[PartidoFixture]
