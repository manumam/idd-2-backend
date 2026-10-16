"""Caso de uso 11: estadísticas de un partido en un intervalo (InfluxDB)."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from app.adapters import influx_adapter
from app.core.exceptions import InvalidRequestError
from app.schemas.estadisticas import EstadisticasResponse, PuntoEstadistica

FORMATO_HORA = "%Y-%m-%dT%H:%M:%SZ"
MAX_INTERVALO_CRUDO = timedelta(minutes=30)   # puntos cada 5 s
MAX_INTERVALO_AGREGADO = timedelta(hours=2)
LIMITE_FILAS = 5000
VENTANAS = {"1m": 60, "5m": 300}


def _parsear_hora(valor: str, campo: str) -> datetime:
    try:
        return datetime.strptime(valor, FORMATO_HORA)
    except ValueError:
        raise InvalidRequestError(f"Parámetros inválidos: {campo}.")


def _validar_intervalo(desde: datetime, hasta: datetime, ventana: Optional[str]) -> None:
    if desde >= hasta:
        raise InvalidRequestError("Parámetros inválidos: 'desde' debe ser anterior a 'hasta'.")
    maximo = MAX_INTERVALO_AGREGADO if ventana else MAX_INTERVALO_CRUDO
    if hasta - desde > maximo:
        minutos = int(maximo.total_seconds() // 60)
        raise InvalidRequestError(f"El intervalo no puede superar {minutos} minutos con esa configuración.")


def _hora(valor: datetime) -> str:
    return valor.strftime(FORMATO_HORA)


def _agregar(filas: list, ventana: str) -> list:
    """Agrupa por ventana y equipo: promedio de posesión, máximo de tiros y suma de pases."""
    segundos = VENTANAS[ventana]
    grupos = defaultdict(list)
    for f in filas:
        instante = datetime.fromisoformat(f["time"])
        minutos = segundos // 60
        inicio = instante.replace(minute=instante.minute - instante.minute % minutos, second=0, microsecond=0)
        grupos[(inicio, f["equipo_id"])].append(f)
    puntos = []
    for (inicio, equipo), valores in sorted(grupos.items()):
        puntos.append(
            PuntoEstadistica(
                hora=_hora(inicio),
                equipo=equipo,
                posesionPct=round(sum(v["posesion_pct"] for v in valores) / len(valores), 1),
                tiros=max(v["tiros_acumulados"] for v in valores),
                pasesIntervalo=sum(v["pases_intervalo"] for v in valores),
            )
        )
    return puntos


def obtener_estadisticas(
    partido: str, desde: str, hasta: str, equipo: Optional[str], ventana: Optional[str]
) -> EstadisticasResponse:
    inicio = _parsear_hora(desde, "desde")
    fin = _parsear_hora(hasta, "hasta")
    _validar_intervalo(inicio, fin, ventana)

    filas = influx_adapter.find_estadisticas(partido, desde, hasta, equipo, LIMITE_FILAS)
    if ventana:
        items = _agregar(filas, ventana)
    else:
        items = [
            PuntoEstadistica(
                hora=_hora(datetime.fromisoformat(f["time"])),
                equipo=f["equipo_id"],
                posesionPct=f["posesion_pct"],
                tiros=f["tiros_acumulados"],
                pasesIntervalo=f["pases_intervalo"],
            )
            for f in filas
        ]
    return EstadisticasResponse(partido=partido, desde=desde, hasta=hasta, ventana=ventana, items=items)
