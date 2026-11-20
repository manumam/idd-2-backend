#!/usr/bin/env python3
"""Simulación en vivo acelerada: MongoDB e InfluxDB avanzan al mismo ritmo de juego."""
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DURACION_SEG = 5400
FACTOR_POR_DEFECTO = 10


class RelojSimulado:
    """Convierte tiempo real transcurrido en segundos de juego: factor 10 juega 90 minutos en 9."""

    def __init__(self, factor=FACTOR_POR_DEFECTO, duracion=DURACION_SEG):
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('El factor debe ser finito y positivo')
        self.factor = factor
        self.duracion = duracion

    def segundo_en(self, transcurrido_real):
        if transcurrido_real < 0:
            raise ValueError('El tiempo real no puede retroceder')
        return min(self.duracion, math.floor(transcurrido_real * self.factor))

    def transcurrido_para(self, segundo):
        return segundo / self.factor

    def pendientes(self, ultimo_escrito, transcurrido_real):
        """Segundos de juego vencidos y todavía no escritos; -1 indica que no se escribió ninguno."""
        return range(ultimo_escrito + 1, self.segundo_en(transcurrido_real) + 1)


def ticks_vencidos(ticks, siguiente, segundo):
    """Índices de los ticks del guion cuyo minuto ya se alcanzó, empezando por `siguiente`."""
    vencidos = []
    for i in range(siguiente, len(ticks)):
        if ticks[i].reloj.minuto * 60 > segundo:
            break
        vencidos.append(i)
    return vencidos
