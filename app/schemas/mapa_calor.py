from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GrillaCancha(BaseModel):
    largo_m: float
    ancho_m: float
    lado_m: float
    columnas: int
    filas: int


class IntervaloMinutos(BaseModel):
    desde_minuto: int
    hasta_minuto: int


class CeldaMapa(BaseModel):
    columna: int
    fila: int
    muestras: int
    intensidad: float = Field(ge=0, le=1)


class MapaCalorResponse(BaseModel):
    partido: str
    jugador: str
    fuente: Optional[Literal["en_vivo", "historico"]] = Field(
        description="`en_vivo`: tracking crudo; `historico`: ocupación materializada; null en un partido próximo")
    grilla: GrillaCancha
    intervalo: Optional[IntervaloMinutos] = Field(description="Minutos efectivos [desde, hasta); null en un partido próximo")
    celdas: List[CeldaMapa]
