"""Detalle MongoDB/Redis; eventos y goleadores históricos aún usan Neo4j."""
import hashlib
import json
import logging
from pydantic import ValidationError

from app.adapters import neo4j_adapter, mongo_adapter, redis_adapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError
from app.services.playoffs_service import consultar_playoffs
from app.core.exceptions import ResourceNotFoundError
from app.schemas.alineaciones import Alineaciones, AlineacionesResponse
from app.core.exceptions import BaseAppException
from app.schemas.equipos import EquipoRef
from app.schemas.partidos import (
    EventoResponse,
    EventosResponse,
    GoleadoresResponse,
    GolResponse,
    JugadorRef,
    PartidoResponse,
    Protagonista,
)


def _partido_no_encontrado(codigo: str) -> ResourceNotFoundError:
    return ResourceNotFoundError("PARTIDO_NO_ENCONTRADO", f"No existe el partido '{codigo}'.")


logger = logging.getLogger(__name__)


def obtener_partido(codigo: str) -> PartidoResponse:
    documento = mongo_adapter.find_partido(codigo)
    if documento is None:
        raise _partido_no_encontrado(codigo)
    datos = {k: v for k, v in documento.items() if k != "_id"}
    datos["codigo"] = documento["_id"]
    if datos["fase"] != "Grupos":
        cruce = next((c for c in consultar_playoffs().items if c.codigo == codigo), None)
        if cruce is not None:
            datos.update(cruce.partido.model_dump())
            datos.update(origen_local=cruce.local.descripcion, origen_visitante=cruce.visitante.descripcion,
                         requiere_revision=cruce.requiere_revision)
            # Un reloj de participantes obsoletos tampoco describe el encuentro actual.
            if cruce.partido.estado == "proximo":
                datos["reloj"] = None
    # Versionado por todas las entradas efectivas: cambios externos, cierres y
    # correcciones dejan de usar la clave anterior sin necesitar escrituras en GET.
    payload = json.dumps(datos, default=str, sort_keys=True, ensure_ascii=False)
    key = f"partido:v1:{codigo}:" + hashlib.sha256(payload.encode()).hexdigest()
    try:
        cached = redis_adapter.get_cache(key)
        if cached is not None:
            # fecha es un campo calculado, no una entrada al modelo.
            value = json.loads(cached)
            value.pop("fecha", None)
            return PartidoResponse.model_validate(value)
    except (DatabaseUnavailableError, ValidationError, UnicodeError, ValueError, TypeError, AttributeError):
        logger.warning("Caché del partido no disponible o inválida")
    respuesta = PartidoResponse.model_validate(datos)
    try:
        redis_adapter.set_cache(key, respuesta.model_dump_json(), settings.fixture_cache_ttl_seconds)
    except DatabaseUnavailableError:
        logger.warning("No se pudo cachear el partido")
    return respuesta


def listar_eventos(codigo: str, limit: int) -> EventosResponse:
    eventos = neo4j_adapter.find_eventos(codigo, limit)
    if eventos is None:
        raise _partido_no_encontrado(codigo)
    items = [
        EventoResponse(
            codigo=e["id"],
            tipo=e["tipo"],
            minuto=e["minuto"],
            protagonistas=[
                Protagonista(jugador=JugadorRef(codigo=j["id"], nombre=j["nombre"]), rol=j["rol"])
                for j in e["protagonistas"]
            ],
        )
        for e in eventos
    ]
    return EventosResponse(partido=codigo, items=items)


def listar_goleadores(sede: str, confederacion: str, limit: int) -> GoleadoresResponse:
    if not neo4j_adapter.sede_existe(sede):
        raise ResourceNotFoundError("SEDE_NO_ENCONTRADA", f"No existe la sede '{sede}'.")
    goles = neo4j_adapter.find_goleadores(sede, confederacion, limit)
    items = [
        GolResponse(
            jugador=JugadorRef(codigo=g["jugador_id"], nombre=g["jugador_nombre"]),
            equipo=EquipoRef(codigo=g["equipo_id"], nombre=g["equipo_nombre"]),
            partido=g["partido"],
            minuto=g["minuto"],
        )
        for g in goles
    ]
    return GoleadoresResponse(sede=sede, confederacion=confederacion, items=items)


def obtener_alineaciones(codigo: str) -> AlineacionesResponse:
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
    key = "alineaciones:v1:" + codigo + ":" + hashlib.sha256(respuesta.model_dump_json().encode()).hexdigest()
    try:
        cached = redis_adapter.get_cache(key)
        if cached is not None:
            value = AlineacionesResponse.model_validate_json(cached)
            if value == respuesta:
                return value
    except (DatabaseUnavailableError, ValidationError, ValueError, TypeError):
        logger.warning("Caché de alineaciones no disponible o inválida")
    try:
        redis_adapter.set_cache(key, respuesta.model_dump_json(), settings.fixture_cache_ttl_seconds)
    except DatabaseUnavailableError:
        logger.warning("No se pudieron cachear las alineaciones")
    return respuesta
