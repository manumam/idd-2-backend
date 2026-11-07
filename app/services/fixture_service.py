"""Listado con Cache-Aside; Redis es una dependencia opcional."""
import logging

from pydantic import ValidationError

from app.adapters import mongo_adapter, redis_adapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.fixture import FixtureResponse

logger = logging.getLogger(__name__)
FIXTURE_CACHE_KEY = "fixture:v1:todos"


def invalidar_fixture() -> bool:
    """Invocar después de confirmar cambios en MongoDB; TTL limita fallos."""
    try:
        redis_adapter.delete_cache(FIXTURE_CACHE_KEY)
        return True
    except DatabaseUnavailableError:
        logger.warning("No se pudo invalidar la caché del fixture")
        return False


def consultar_fixture() -> FixtureResponse:
    try:
        cached = redis_adapter.get_cache(FIXTURE_CACHE_KEY)
        if cached is not None:
            return FixtureResponse.model_validate_json(cached)
    except (DatabaseUnavailableError, ValidationError, UnicodeError):
        logger.warning("Caché del fixture no disponible o inválida")

    documentos = mongo_adapter.list_fixture()
    respuesta = FixtureResponse(items=[
        dict(codigo=d["_id"], **{k: v for k, v in d.items() if k != "_id"})
        for d in documentos
    ])
    try:
        redis_adapter.set_cache(
            FIXTURE_CACHE_KEY, respuesta.model_dump_json(), settings.fixture_cache_ttl_seconds
        )
    except DatabaseUnavailableError:
        logger.warning("No se pudo guardar la caché del fixture")
    return respuesta
