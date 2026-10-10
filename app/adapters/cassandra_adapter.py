"""Adaptador para Apache Cassandra (Módulo Tabular: Comentarios de Partidos).

Encapsula Cluster, Session y ExecutionProfiles con control de timeouts (RF5, RNF5, RNF8).
"""

import logging
from typing import Optional
from cassandra.cluster import Cluster, Session, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.cluster import NoHostAvailable

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class CassandraAdapter(BaseAdapter):
    """Encapsula el cluster y sesión nativa de Cassandra."""

    def __init__(self):
        self._cluster: Optional[Cluster] = None
        self._session: Optional[Session] = None

    def connect(self) -> Session:
        """Inicializa el cluster y sesión sobre el keyspace configurado."""
        if self._session is None:
            try:
                profile = ExecutionProfile(
                    request_timeout=settings.db_timeout_seconds,
                    load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="datacenter1"),
                )
                self._cluster = Cluster(
                    contact_points=settings.cassandra_hosts,
                    port=settings.cassandra_port,
                    connect_timeout=settings.db_timeout_seconds,
                    execution_profiles={EXEC_PROFILE_DEFAULT: profile},
                )
                self._session = self._cluster.connect(settings.cassandra_keyspace)
            except Exception as e:
                logger.error("Error al conectar con Cassandra: %s", e)
                raise DatabaseUnavailableError("Cassandra", e)
        return self._session

    @property
    def session(self) -> Session:
        """Acceso a la sesión activa en el keyspace."""
        return self.connect()

    def ping(self) -> bool:
        """Verifica la conectividad activa contra Cassandra."""
        try:
            session = self.connect()
            # Consulta liviana sobre tabla del sistema para validar conexión
            session.execute("SELECT release_version FROM system.local")
            return True
        except (NoHostAvailable, Exception) as e:
            logger.warning("Fallo en ping Cassandra: %s", e)
            raise DatabaseUnavailableError("Cassandra", e)

    def close(self) -> None:
        """Cierra la sesión y el cluster de Cassandra."""
        if self._session is not None:
            self._session.shutdown()
            self._session = None
        if self._cluster is not None:
            self._cluster.shutdown()
            self._cluster = None


cassandra_adapter = CassandraAdapter()
