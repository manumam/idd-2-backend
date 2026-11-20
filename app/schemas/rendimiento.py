"""Caso 9: métricas individuales y cobertura de las fuentes."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.equipos import EquipoRef
from app.schemas.partidos import JugadorRef, RelojPartido


class MetricasJugador(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    goles: int | None = Field(default=None, ge=0)
    asistencias: int | None = Field(default=None, ge=0)
    tarjetas_amarillas: int | None = Field(default=None, ge=0)
    tarjetas_rojas: int | None = Field(default=None, ge=0)
    distancia_m: float | None = Field(default=None, ge=0)
    velocidad_max_kmh: float | None = Field(default=None, ge=0)


class RendimientoResponse(BaseModel):
    partido: str
    jugador: JugadorRef
    equipo: EquipoRef
    estado: Literal['proximo', 'en_vivo', 'finalizado']
    consolidacion: Literal['sin_datos', 'pendiente', 'provisional', 'completa']
    reloj: RelojPartido | None = None
    actualizado_en: datetime | None = None
    metricas: MetricasJugador = Field(default_factory=MetricasJugador)
    advertencias: list[str] = Field(default_factory=list)


class AcumuladosJugadorResponse(BaseModel):
    jugador: JugadorRef
    equipo: EquipoRef
    consolidacion: Literal['sin_datos', 'pendiente', 'provisional', 'completa']
    metricas: MetricasJugador = Field(default_factory=MetricasJugador)
    partidos: list[RendimientoResponse] = Field(default_factory=list)
    partidos_consolidados: int = 0
    partidos_pendientes: int = 0
    advertencias: list[str] = Field(default_factory=list)


class IntervaloTracking(BaseModel):
    """Extremos inclusivos: primera muestra = base del odómetro, frecuencia 1 Hz."""
    model_config = ConfigDict(extra='forbid')
    desde: datetime
    hasta: datetime
    muestras: int = Field(ge=1, le=14401, strict=True)

    @model_validator(mode='after')
    def cobertura(self):
        if not self.desde.tzinfo or not self.hasta.tzinfo:
            raise ValueError('El tracking requiere zona horaria')
        segundos = (self.hasta - self.desde).total_seconds()
        if segundos < 0 or segundos != int(segundos) or self.muestras != segundos + 1:
            raise ValueError('Cantidad incompatible con tracking a 1 Hz')
        if self.desde.microsecond or self.hasta.microsecond:
            raise ValueError('Las muestras deben estar alineadas al segundo')
        return self


class ControlTracking(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    completa: bool
    jugadores: dict[str, list[IntervaloTracking]]

    @model_validator(mode='after')
    def intervalos_disjuntos(self):
        import re
        if not self.jugadores or len(self.jugadores) > 52:
            raise ValueError('Se requieren de uno a 52 jugadores')
        for codigo, intervalos in self.jugadores.items():
            if not re.fullmatch(r'[A-Z]{3}-[1-9][0-9]?', codigo):
                raise ValueError('Código de jugador inválido')
            if sum(i.muestras for i in intervalos) > 14401:
                raise ValueError('Tracking individual excede cuatro horas')
            ordenados = sorted(intervalos, key=lambda i: i.desde)
            if any(b.desde <= a.hasta for a, b in zip(ordenados, ordenados[1:])):
                raise ValueError('Intervalos de tracking superpuestos')
        return self
