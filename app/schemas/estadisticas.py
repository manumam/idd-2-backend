from typing import List, Optional

from pydantic import BaseModel


class PuntoEstadistica(BaseModel):
    hora: str
    equipo: str
    posesionPct: float
    tiros: int
    pasesIntervalo: int


class EstadisticasResponse(BaseModel):
    partido: str
    desde: str
    hasta: str
    ventana: Optional[str] = None
    items: List[PuntoEstadistica]
