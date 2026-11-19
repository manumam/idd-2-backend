"""Cache-Aside de partido, eventos, alineaciones, posiciones y cuadro; Redis es opcional."""
import logging
from typing import Optional, TypeVar

from pydantic import BaseModel, ValidationError

from app.adapters import mongo_adapter, redis_adapter
from app.adapters.redis_adapter import borrar_por_patron
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError
from app.core.metrics import record_cache

logger = logging.getLogger(__name__)
Modelo = TypeVar("Modelo", bound=BaseModel)

PLAYOFFS_CACHE_KEY = "playoffs:v2:todos"
PATRONES_DERIVADOS = ("partido:v2:*", "eventos:v2:*", "alineaciones:v2:*", "grupos:v2:*", PLAYOFFS_CACHE_KEY)
FUNCIONALIDAD_POR_NAMESPACE = {
    "partido": "partido", "eventos": "eventos", "alineaciones": "alineaciones",
    "grupos": "posiciones", "playoffs": "playoffs",
}


def clave_partido(codigo: str) -> str:
    return f"partido:v2:{codigo}"


def clave_eventos(codigo: str, limit: int, skip: int) -> str:
    return f"eventos:v2:{codigo}:{limit}:{skip}"


def patron_eventos(codigo: str) -> str:
    return f"eventos:v2:{codigo}:*"


def clave_alineaciones(codigo: str) -> str:
    return f"alineaciones:v2:{codigo}"


def clave_posiciones(grupo: str) -> str:
    return f"grupos:v2:{grupo}"


def leer_cache(key: str, modelo: type[Modelo]) -> Optional[Modelo]:
    namespace = key.split(":", 1)[0]
    funcionalidad = FUNCIONALIDAD_POR_NAMESPACE[namespace]
    try:
        cached = redis_adapter.get_cache(key)
        if cached is not None:
            respuesta = modelo.model_validate_json(cached)
            logger.info("%s_cache=hit", namespace)
            record_cache(funcionalidad, "hit")
            return respuesta
    except (DatabaseUnavailableError, ValidationError, UnicodeError):
        logger.warning("Caché %s no disponible o inválida", namespace)
        record_cache(funcionalidad, "error")
        return None
    logger.info("%s_cache=miss", namespace)
    record_cache(funcionalidad, "miss")
    return None


def guardar_cache(key: str, respuesta: BaseModel) -> None:
    payload = respuesta.model_dump_json(exclude=set(type(respuesta).model_computed_fields))
    try:
        redis_adapter.set_cache(key, payload, settings.fixture_cache_ttl_seconds)
    except DatabaseUnavailableError:
        logger.warning("No se pudo guardar la caché %s", key.split(":", 1)[0])


def _borrar_partido(codigo: str) -> None:
    redis_adapter.delete_cache(clave_partido(codigo))
    redis_adapter.delete_cache(clave_alineaciones(codigo))
    redis_adapter.delete_cache_matching(patron_eventos(codigo))


def invalidar_resultado(codigo: str, grupo: Optional[str]) -> bool:
    """Invocar después de confirmar en MongoDB un cambio de eventos, marcador, reloj o estado."""
    try:
        _borrar_partido(codigo)
        if grupo:
            redis_adapter.delete_cache(clave_posiciones(grupo))
        redis_adapter.delete_cache(PLAYOFFS_CACHE_KEY)
        # Cualquier resultado puede mover el cuadro, y el cuadro define participantes
        # y estado de cada cruce eliminatorio: sus detalles también quedan obsoletos.
        for cruce in mongo_adapter.list_cruces():
            _borrar_partido(cruce["_id"])
        return True
    except DatabaseUnavailableError:
        logger.warning("No se pudo invalidar la caché del partido; el TTL limita la antigüedad")
        return False


def borrar_cache_derivada(cliente) -> None:
    """Para cargas masivas desde scripts, que usan su propio cliente Redis."""
    for patron in PATRONES_DERIVADOS:
        borrar_por_patron(cliente, patron)


def conectar_cache(config):
    """Cliente Redis para scripts de carga, con su propia configuración."""
    from redis import Redis
    return Redis(host=config.redis_host, port=config.redis_port, db=config.redis_db,
                 password=config.redis_password or None, socket_connect_timeout=2, socket_timeout=2)
