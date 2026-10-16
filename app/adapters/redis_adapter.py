"""Adaptador para Redis (Módulo Clave/Valor: Sesiones y Caché).

Encapsula cliente Redis con pool de conexiones y timeouts (RF6, RNF5, RNF8).
"""

import logging
from typing import Any, Callable, Dict, Optional
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class RedisAdapter(BaseAdapter):
    """Encapsula el cliente Redis oficial."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    def get_client(self) -> redis.Redis:
        """Obtiene o inicializa el cliente Redis."""
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                    socket_connect_timeout=settings.db_timeout_seconds,
                    socket_timeout=settings.db_timeout_seconds,
                    decode_responses=True,
                    retry=Retry(NoBackoff(), 0),  # sin reintentos: falla dentro del timeout
                )
            except Exception as e:
                logger.error("Error al inicializar cliente Redis: %s", e)
                raise DatabaseUnavailableError("Redis", e)
        return self._client

    @property
    def client(self) -> redis.Redis:
        """Acceso al cliente Redis."""
        return self.get_client()

    def _execute(self, operation: Callable[[], Any]) -> Any:
        """Ejecuta una operación y traduce los errores del cliente a 'fuente no disponible'."""
        try:
            return operation()
        except RedisError as e:
            logger.warning("Fallo en operación Redis: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("Redis", e) from e

    def get_sesion(self, sesion_id: str) -> Optional[Dict[str, Any]]:
        """Lee el hash de la sesión y su TTL restante; None si no existe o expiró."""
        clave = f"sesion:{sesion_id}"

        def lectura() -> Optional[Dict[str, Any]]:
            pipe = self.client.pipeline(transaction=False)
            pipe.hgetall(clave)
            pipe.ttl(clave)
            campos, ttl = pipe.execute()
            if not campos:
                return None
            return {"campos": campos, "ttl": ttl}

        return self._execute(lectura)

    def delete_sesion(self, sesion_id: str) -> None:
        """Invalida la sesión. Es idempotente: borrar una clave ausente no falla."""
        self._execute(lambda: self.client.delete(f"sesion:{sesion_id}"))

    def ping(self) -> bool:
        """Verifica la conectividad activa contra Redis."""
        try:
            client = self.get_client()
            return bool(client.ping())
        except (ConnectionError, TimeoutError, RedisError, Exception) as e:
            logger.warning("Fallo en ping Redis: %s", e)
            raise DatabaseUnavailableError("Redis", e)

    def close(self) -> None:
        """Cierra el pool de conexiones de Redis."""
        if self._client is not None:
            self._client.close()
            self._client = None


redis_adapter = RedisAdapter()
