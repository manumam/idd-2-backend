"""Caso de uso 10: mapa de calor de un jugador en un partido (InfluxDB)."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.adapters import influx_adapter, mongo_adapter
from app.core.exceptions import InvalidRequestError, ResourceNotFoundError
from app.schemas.mapa_calor import CeldaMapa, GrillaCancha, IntervaloMinutos, MapaCalorResponse
from app.schemas.partidos import PartidoResponse
from app.services import partidos_service
from app.services.grilla_cancha import (
    COLUMNAS, FILAS, Celda, celda_desde_id, celdas_con_intensidad, parametros_grilla)

# Tiempo reglamentario más prórroga; coincide con el máximo del reloj del partido.
MINUTO_MAXIMO = 120
FORMATO_HORA = "%Y-%m-%dT%H:%M:%SZ"


def _grilla() -> GrillaCancha:
    medidas = parametros_grilla()
    return GrillaCancha(largo_m=medidas["largo_m"], ancho_m=medidas["ancho_m"], lado_m=medidas["lado_m"],
                        columnas=COLUMNAS, filas=FILAS)


def _validar_rango(desde: int, hasta: int) -> None:
    if desde >= hasta:
        raise InvalidRequestError("Parámetros inválidos: 'desde_minuto' debe ser anterior a 'hasta_minuto'.")


def _validar_jugador(jugador: str, partido: PartidoResponse) -> None:
    documento = mongo_adapter.find_jugador(jugador)
    equipos = {e.codigo for e in (partido.local, partido.visitante) if e}
    if documento is None or documento["equipo"]["_id"] not in equipos:
        raise ResourceNotFoundError(
            "JUGADOR_NO_ENCONTRADO", f"El jugador '{jugador}' no pertenece a las selecciones del partido.")


def _minuto_transcurrido(partido: PartidoResponse) -> int:
    if partido.reloj is None:
        return MINUTO_MAXIMO
    return min(partido.reloj.minuto + partido.reloj.adicional + 1, MINUTO_MAXIMO)


def _inicio_tracking(partido: PartidoResponse) -> datetime:
    # El simulador registra inicio_tracking al empezar; los datos precargados arrancan en fecha_hora.
    # Anclar en uno solo evita mezclar muestras simuladas con las precargadas del mismo partido.
    inicio = mongo_adapter.find_inicio_tracking(partido.codigo)
    if inicio is None:
        return partido.fecha_hora
    inicio = inicio.replace(tzinfo=timezone.utc) if inicio.tzinfo is None else inicio.astimezone(timezone.utc)
    # Las ventanas materializadas empiezan en minutos exactos; se ancla igual para que ambas fuentes coincidan.
    return inicio.replace(second=0, microsecond=0)


def _hora(inicio: datetime, minuto: int) -> str:
    return (inicio + timedelta(minutes=minuto)).strftime(FORMATO_HORA)


def leer_mapa_crudo(partido: str, jugador: str, inicio: datetime, desde: int, hasta: int) -> dict[Celda, int]:
    filas = influx_adapter.contar_muestras_por_celda(
        partido, jugador, _hora(inicio, desde), _hora(inicio, hasta), parametros_grilla())
    return {Celda(int(f["columna"]), int(f["fila"])): int(f["muestras"]) for f in filas}


def leer_mapa_historico(partido: str, jugador: str, inicio: datetime, desde: int, hasta: int) -> dict[Celda, int]:
    filas = influx_adapter.sumar_ocupacion_por_celda(partido, jugador, _hora(inicio, desde), _hora(inicio, hasta))
    muestras = {}
    for f in filas:
        celda = celda_desde_id(f["celda"])
        if celda is not None:
            muestras[celda] = int(f["muestras"])
    return muestras


def _leer_mapa(detalle: PartidoResponse, jugador: str, desde: int, hasta: int) -> tuple[str, dict[Celda, int]]:
    inicio = _inicio_tracking(detalle)
    if detalle.estado == "finalizado":
        muestras = leer_mapa_historico(detalle.codigo, jugador, inicio, desde, hasta)
        if muestras:
            return "historico", muestras
        # Sin ocupación materializada (todavía no se ejecutó el script) se usa el crudo mientras no venza.
    return "en_vivo", leer_mapa_crudo(detalle.codigo, jugador, inicio, desde, hasta)


def obtener_mapa_calor(
    partido: str, jugador: str, desde_minuto: Optional[int], hasta_minuto: Optional[int]
) -> MapaCalorResponse:
    if desde_minuto is not None and hasta_minuto is not None:
        _validar_rango(desde_minuto, hasta_minuto)
    detalle = partidos_service.obtener_partido(partido)
    _validar_jugador(jugador, detalle)
    if detalle.estado == "proximo":
        return MapaCalorResponse(partido=partido, jugador=jugador, fuente=None, grilla=_grilla(),
                                 intervalo=None, celdas=[])

    desde = desde_minuto if desde_minuto is not None else 0
    hasta = hasta_minuto if hasta_minuto is not None else _minuto_transcurrido(detalle)
    _validar_rango(desde, hasta)
    fuente, muestras = _leer_mapa(detalle, jugador, desde, hasta)
    return MapaCalorResponse(
        partido=partido, jugador=jugador, fuente=fuente, grilla=_grilla(),
        intervalo=IntervaloMinutos(desde_minuto=desde, hasta_minuto=hasta),
        celdas=[CeldaMapa(**c) for c in celdas_con_intensidad(muestras)],
    )
