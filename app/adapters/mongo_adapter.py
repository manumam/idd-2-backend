"""Adaptador para MongoDB (Módulo Documental: Equipos y Jugadores).

Encapsula MongoClient, selección de base de datos y control de timeouts (RF3, RNF5, RNF8).
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from app.adapters.base import BaseAdapter
from app.core.observability import observe
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


_PROYECCION_JUGADOR = {
    "nombre": 1, "apellido": 1, "dorsal": 1, "posicion": 1,
    "fecha_nacimiento": 1, "club": 1, "capitan": 1, "equipo._id": 1, "equipo.nombre": 1,
}


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
                logger.error("Error al inicializar cliente MongoDB: %s", e.__class__.__name__)
                raise DatabaseUnavailableError("MongoDB", e)
        return self._db

    @property
    def db(self) -> Database:
        """Acceso a la base de datos configurada."""
        return self.connect()

    def _execute(self, operation: Callable[[], Any]) -> Any:
        """Ejecuta una operación y traduce los errores del driver a 'fuente no disponible'."""
        try:
            return operation()
        except PyMongoError as e:
            logger.warning("Fallo en operación MongoDB: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("MongoDB", e) from e

    @observe("MongoDB")
    def find_equipo(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Busca un equipo por _id (código FIFA) con los campos del contrato."""
        proyeccion = {
            "nombre": 1, "confederacion": 1, "grupo": 1,
            "ranking_fifa": 1, "director_tecnico": 1, "anfitrion": 1,
        }
        return self._execute(lambda: self.db["equipos"].find_one({"_id": codigo}, proyeccion))

    @observe("MongoDB")
    def find_jugador(self, codigo: str) -> Optional[Dict[str, Any]]:
        """Busca un jugador por _id (<equipo>-<dorsal>)."""
        return self._execute(lambda: self.db["jugadores"].find_one({"_id": codigo}, _PROYECCION_JUGADOR))

    @observe("MongoDB")
    def list_jugadores(
        self, equipo: str, posicion: Optional[str], limit: int, skip: int
    ) -> List[Dict[str, Any]]:
        """Plantel de un equipo, opcionalmente por posición, paginado y ordenado por dorsal.

        Filtra por el prefijo de los índices (equipo._id, dorsal) y (equipo._id, posicion).
        Con `posicion` ordena en memoria, acotado al plantel de un equipo.
        """
        filtro: Dict[str, Any] = {"equipo._id": equipo}
        if posicion:
            filtro["posicion"] = posicion

        def consulta() -> List[Dict[str, Any]]:
            cursor = (
                self.db["jugadores"]
                .find(filtro, _PROYECCION_JUGADOR)
                .sort("dorsal", 1)
                .skip(skip)
                .limit(limit)
            )
            return list(cursor)

        return self._execute(consulta)

    @observe("MongoDB")
    def ping(self) -> bool:
        """Verifica la conectividad activa contra MongoDB."""
        try:
            database = self.connect()
            database.command("ping")
            return True
        except (ServerSelectionTimeoutError, PyMongoError, Exception) as e:
            logger.warning("Fallo en ping MongoDB: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("MongoDB", e)

    def close(self) -> None:
        """Cierra el pool de conexiones de MongoDB."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None


mongo_adapter = MongoAdapter()
