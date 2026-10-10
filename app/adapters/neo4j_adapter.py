"""Adaptador para Neo4j (Módulo de Grafos: Partidos y Eventos).

Encapsula el driver Bolt oficial y sesiones para consultas Cypher parametrizadas (RF4, RNF5).
"""

import logging
from typing import Optional
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class Neo4jAdapter(BaseAdapter):
    """Encapsula el driver Bolt de Neo4j."""

    def __init__(self):
        self._driver: Optional[Driver] = None

    def get_driver(self) -> Driver:
        """Obtiene o inicializa el driver de Neo4j."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_user, settings.neo4j_password),
                    connection_timeout=settings.db_timeout_seconds,
                    max_connection_lifetime=3600,
                )
            except Exception as e:
                logger.error("Error al inicializar driver Neo4j: %s", e)
                raise DatabaseUnavailableError("Neo4j", e)
        return self._driver

    def ping(self) -> bool:
        """Verifica conectividad y autenticación contra Neo4j."""
        try:
            driver = self.get_driver()
            driver.verify_connectivity()
            return True
        except (ServiceUnavailable, Neo4jError, Exception) as e:
            logger.warning("Fallo en ping Neo4j: %s", e)
            raise DatabaseUnavailableError("Neo4j", e)

    def close(self) -> None:
        """Cierra el driver de Neo4j."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


neo4j_adapter = Neo4jAdapter()
