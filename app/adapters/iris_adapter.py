"""Adaptador para InterSystems IRIS (Módulo Objetos Persistentes: Dominio Complejo).

Encapsula la conexión nativa con InterSystems IRIS y ejecución de consultas de dominio (RF8, RNF5).
"""

import logging
from typing import Optional, Any
import iris

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class IrisAdapter(BaseAdapter):
    """Encapsula el driver nativo de InterSystems IRIS."""

    def __init__(self):
        self._connection: Optional[Any] = None

    def connect(self) -> Any:
        """Inicializa la conexión con el Superserver de InterSystems IRIS."""
        if self._connection is None:
            try:
                self._connection = iris.createConnection(
                    settings.iris_host,
                    settings.iris_port,
                    settings.iris_namespace,
                    settings.iris_user,
                    settings.iris_password,
                )
            except Exception as e:
                logger.error("Error al conectar con InterSystems IRIS: %s", e)
                raise DatabaseUnavailableError("IRIS", e)
        return self._connection

    @property
    def iris_context(self) -> Any:
        """Retorna el objeto context/gateway nativo de IRIS para invocar clases."""
        conn = self.connect()
        try:
            return iris.createIRIS(conn)
        except Exception as e:
            logger.error("Error al obtener contexto IRIS: %s", e)
            raise DatabaseUnavailableError("IRIS", e)

    def ping(self) -> bool:
        """Verifica la conectividad activa contra InterSystems IRIS."""
        try:
            conn = self.connect()
            # Si la conexión nativa está viva, creamos el handler IRIS y ejecutamos un chequeo básico
            iris_obj = iris.createIRIS(conn)
            # Invoca una función del sistema o evalúa objeto básico
            _ = iris_obj.classMethodValue("%SYSTEM.Version", "GetVersion")
            return True
        except Exception as e:
            logger.warning("Fallo en ping InterSystems IRIS: %s", e)
            raise DatabaseUnavailableError("IRIS", e)

    def close(self) -> None:
        """Cierra la conexión con InterSystems IRIS."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


iris_adapter = IrisAdapter()
