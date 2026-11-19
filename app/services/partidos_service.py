"""Detalle, eventos y alineaciones desde MongoDB con caché Redis."""
from typing import Callable

from pydantic import ValidationError

from app.adapters import mongo_adapter
from app.services.cache_partidos import (
    clave_alineaciones, clave_eventos, clave_partido, guardar_cache, leer_cache)
from app.services.playoffs_service import consultar_playoffs
from app.core.exceptions import ResourceNotFoundError
from app.schemas.alineaciones import Alineaciones, AlineacionesResponse
from app.core.exceptions import BaseAppException
from app.schemas.playoffs import PlayoffsResponse
from app.schemas.partidos import (
    EventoResponse,
    EventosResponse,
    PartidoResponse,
)


def _partido_no_encontrado(codigo: str) -> ResourceNotFoundError:
    return ResourceNotFoundError("PARTIDO_NO_ENCONTRADO", f"No existe el partido '{codigo}'.")


def obtener_partido(codigo: str) -> PartidoResponse:
    key = clave_partido(codigo)
    cached = leer_cache(key, PartidoResponse)
    if cached is not None:
        return cached
    documento = mongo_adapter.find_partido(codigo)
    if documento is None:
        raise _partido_no_encontrado(codigo)
    respuesta = _detalle_documento(documento)
    guardar_cache(key, respuesta)
    return respuesta


def _detalle_documento(documento: dict,
                       cuadro: Callable[[], PlayoffsResponse] = consultar_playoffs) -> PartidoResponse:
    codigo = documento["_id"]
    datos = {k: v for k, v in documento.items() if k not in ("_id", "eventos", "actualizado_en")}
    datos["codigo"] = documento["_id"]
    if datos["fase"] != "Grupos":
        cruce = next((c for c in cuadro().items if c.codigo == codigo), None)
        if cruce is not None:
            datos.update(cruce.partido.model_dump())
            datos.update(origen_local=cruce.local.descripcion, origen_visitante=cruce.visitante.descripcion,
                         requiere_revision=cruce.requiere_revision)
            # Un reloj de participantes obsoletos tampoco describe el encuentro actual.
            if cruce.partido.estado == "proximo":
                datos["reloj"] = None
    return PartidoResponse.model_validate(datos)


def listar_eventos(codigo: str, limit: int, skip: int = 0) -> EventosResponse:
    key = clave_eventos(codigo, limit, skip)
    cached = leer_cache(key, EventosResponse)
    if cached is not None:
        return cached
    documento = mongo_adapter.find_eventos(codigo)
    if documento is None:
        raise _partido_no_encontrado(codigo)
    partido = _detalle_documento(documento)
    try:
        eventos = [EventoResponse.model_validate(e) for e in documento.get("eventos", [])]
        equipos = {e.codigo for e in (partido.local, partido.visitante) if e}
        if any(e.equipo.codigo not in equipos for e in eventos):
            if documento["fase"] == "Grupos":
                raise ValueError("Equipo ajeno al partido")
            eventos = []  # Una plaza corregida no hereda los eventos del cruce anterior.
        if partido.requiere_revision or partido.estado == "proximo":
            eventos = []
        if len({e.codigo for e in eventos}) != len(eventos):
            raise ValueError("Identificadores de evento repetidos")
    except (ValidationError, ValueError, TypeError) as exc:
        raise BaseAppException("EVENTOS_INVALIDOS", "Los eventos requieren revisión.") from exc
    eventos.sort(key=lambda e: (e.minuto, e.adicional, e.codigo))
    total = len(eventos)
    respuesta = EventosResponse(partido=codigo, items=eventos[skip:skip + limit], total=total,
        siguiente_skip=skip + limit if skip + limit < total else None,
        estado=partido.estado, resultado=partido.resultado, reloj=partido.reloj)
    guardar_cache(key, respuesta)
    return respuesta


def obtener_alineaciones(codigo: str) -> AlineacionesResponse:
    key = clave_alineaciones(codigo)
    cached = leer_cache(key, AlineacionesResponse)
    if cached is not None:
        return cached
    # Reutiliza las plazas efectivas: una corrección del cuadro no debe mostrar
    # la convocatoria de la selección que ocupaba antes esa plaza.
    partido = obtener_partido(codigo)
    documento = mongo_adapter.find_alineaciones(codigo)
    if documento is None:
        raise _partido_no_encontrado(codigo)
    try:
        raw = documento.get("alineaciones")
        alineaciones = Alineaciones.model_validate({} if raw is None else raw)
    except ValidationError as exc:
        raise BaseAppException("ALINEACIONES_INVALIDAS", "Las alineaciones requieren revisión.") from exc
    datos = alineaciones.model_dump()
    for lado in ("local", "visitante"):
        equipo = getattr(partido, lado)
        if datos[lado] and (equipo is None or datos[lado]["equipo"]["codigo"] != equipo.codigo):
            datos[lado] = None
    respuesta = AlineacionesResponse(partido=codigo, **datos)
    guardar_cache(key, respuesta)
    return respuesta
