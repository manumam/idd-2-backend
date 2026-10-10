"""Adaptador para MongoDB (Módulo Documental: Equipos y Jugadores).

Encapsula MongoClient, selección de base de datos y control de timeouts (RF3, RNF5, RNF8).
"""

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class MongoAdapter(BaseAdapter):
    """Encapsula el cliente nativo de MongoDB."""

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> Database:
        """Obtiene o inicializa la conexión con MongoDB."""
        if self._client is None:
            try:
                timeout_ms = int(settings.db_timeout_seconds * 1000)
                self._client = MongoClient(
                    settings.mongo_uri,
                    serverSelectionTimeoutMS=timeout_ms,
                    connectTimeoutMS=timeout_ms,
                    socketTimeoutMS=timeout_ms,
                )
                self._db = self._client[settings.mongo_database]
            except Exception as e:
                logger.error("Error al inicializar cliente MongoDB: %s", e)
                raise DatabaseUnavailableError("MongoDB", e)
        return self._db

    @property
    def db(self) -> Database:
        """Acceso a la base de datos configurada."""
        return self.connect()

    def ping(self) -> bool:
        """Verifica la conectividad activa contra MongoDB."""
        try:
            database = self.connect()
            database.command("ping")
            return True
        except (ServerSelectionTimeoutError, PyMongoError, Exception) as e:
            logger.warning("Fallo en ping MongoDB: %s", e)
            raise DatabaseUnavailableError("MongoDB", e)

    def close(self) -> None:
        """Cierra el pool de conexiones de MongoDB."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None


mongo_adapter = MongoAdapter()
