"""Adaptador para InfluxDB 3 (Módulo Temporal: Estadísticas de Partidos).

Encapsula la API HTTP/SQL de InfluxDB 3 Core con lectura automática de tokens y timeouts (RF7, RNF5, RNF8).
"""

import os
import logging
from typing import Optional, Dict, Any
import requests

from app.adapters.base import BaseAdapter
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class InfluxAdapter(BaseAdapter):
    """Encapsula llamadas HTTP/SQL a InfluxDB 3 Core."""

    def __init__(self):
        self._token: Optional[str] = None
        self._session: Optional[requests.Session] = None

    def _resolve_token(self) -> Optional[str]:
        """Obtiene el token desde configuración o desde archivo local .influxdb3-token."""
        if self._token:
            return self._token

        if settings.influx_token:
            self._token = settings.influx_token
            return self._token

        # Rutas comunes donde la práctica genera el token administrativo
        candidate_paths = [
            ".influxdb3-token",
            os.path.expanduser("~/.influxdb3-token"),
            os.path.abspath("../TP/fixture2030-influxdb/.influxdb3-token"),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        token_val = f.read().strip()
                        if token_val:
                            self._token = token_val
                            return self._token
                except Exception as e:
                    logger.debug("No se pudo leer token en %s: %s", path, e)
        return None

    def get_session(self) -> requests.Session:
        """Obtiene la sesión HTTP reutilizable."""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def ping(self) -> bool:
        """Verifica la conectividad llamando al endpoint /health de InfluxDB 3."""
        try:
            session = self.get_session()
            url = f"{settings.influx_url.rstrip('/')}/health"
            headers = {}
            token = self._resolve_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = session.get(url, headers=headers, timeout=settings.db_timeout_seconds)
            if response.status_code == 200:
                return True
            logger.warning("InfluxDB health retornó status %s", response.status_code)
            raise DatabaseUnavailableError("InfluxDB")
        except requests.RequestException as e:
            logger.warning("Fallo en ping InfluxDB: %s", e)
            raise DatabaseUnavailableError("InfluxDB", e)

    def query_sql(self, query: str) -> Dict[str, Any]:
        """Ejecuta una consulta SQL contra la base temporal configurada."""
        token = self._resolve_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{settings.influx_url.rstrip('/')}/api/v3/query_sql"
        payload = {
            "db": settings.influx_database,
            "query": query,
        }

        try:
            session = self.get_session()
            response = session.post(
                url,
                json=payload,
                headers=headers,
                timeout=settings.db_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("Error al consultar InfluxDB: %s", e)
            raise DatabaseUnavailableError("InfluxDB", e)

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session is not None:
            self._session.close()
            self._session = None


influx_adapter = InfluxAdapter()
