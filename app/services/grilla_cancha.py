"""Grilla fija de la cancha para mapas de calor; la misma en vivo e histórico.

InfluxDB calcula la celda de cada muestra y cuenta por celda; este módulo aporta las medidas
que recibe esa consulta, el id de celda que se guarda como tag y la intensidad de la respuesta.
"""
import math
from typing import NamedTuple

LARGO_CANCHA_M = 105.0
ANCHO_CANCHA_M = 68.0
# Celda de 5 × 5 m: unidad espacial acordada en docs/modelo-tecnico-demo.md (21 × 14 = 294 celdas).
LADO_CELDA_M = 5.0
COLUMNAS = math.ceil(LARGO_CANCHA_M / LADO_CELDA_M)
FILAS = math.ceil(ANCHO_CANCHA_M / LADO_CELDA_M)


class Celda(NamedTuple):
    columna: int
    fila: int


def parametros_grilla() -> dict[str, float | int]:
    # La consulta descarta muestras fuera de la cancha y lleva el borde lejano a la última celda;
    # sin ese tope, x = 105 caería en una columna 22.
    return {
        "largo_m": LARGO_CANCHA_M,
        "ancho_m": ANCHO_CANCHA_M,
        "lado_m": LADO_CELDA_M,
        "ultima_columna": COLUMNAS - 1,
        "ultima_fila": FILAS - 1,
    }


def id_celda(celda: Celda) -> str:
    return f"{celda.columna}_{celda.fila}"


def celda_desde_id(valor: str) -> Celda | None:
    partes = valor.split("_")
    if len(partes) != 2 or not all(p.isdigit() for p in partes):
        return None
    columna, fila = int(partes[0]), int(partes[1])
    if columna >= COLUMNAS or fila >= FILAS:
        return None
    return Celda(columna, fila)


def celdas_con_intensidad(muestras_por_celda: dict[Celda, int]) -> list[dict]:
    # Se cuentan muestras por celda: promediar x/y daría un punto, no la distribución de posiciones.
    # Las celdas ausentes valen cero y no se devuelven.
    maximo = max(muestras_por_celda.values(), default=0)
    if maximo <= 0:
        return []
    return [
        {"columna": c.columna, "fila": c.fila, "muestras": n, "intensidad": n / maximo}
        for c, n in sorted(muestras_por_celda.items())
        if n > 0
    ]
