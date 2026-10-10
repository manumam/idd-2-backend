"""Adaptador para Redis (Módulo Clave/Valor: Sesiones y Caché).

Encapsula cliente Redis con pool de conexiones y timeouts (RF6, RNF5, RNF8).
"""

import logging
from typing import Optional
import redis
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
                )
            except Exception as e:
                logger.error("Error al inicializar cliente Redis: %s", e)
                raise DatabaseUnavailableError("Redis", e)
        return self._client

    @property
    def client(self) -> redis.Redis:
        """Acceso al cliente Redis."""
        return self.get_client()

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
