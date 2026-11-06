from pydantic import BaseModel


class EventoObjeto(BaseModel):
    id: str
    tipo: str
    minuto: int
    partidoId: str


class PartidoObjeto(BaseModel):
    id: str
    codigo: str
    estado: str
    eventos: list[EventoObjeto]
    limit: int
    skip: int
