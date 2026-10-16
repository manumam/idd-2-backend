"""Adaptador para InfluxDB 3 (Módulo Temporal: Estadísticas de Partidos).

Encapsula la API HTTP/SQL de InfluxDB 3 Core con lectura automática de tokens y timeouts (RF7, RNF5, RNF8).
"""

import os
import logging
from typing import Any, Dict, List, Optional
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

    def find_estadisticas(
        self, partido_id: str, desde: str, hasta: str, equipo_id: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Puntos de estadisticas_partido de un partido en [desde, hasta), ordenados por hora."""
        filtro_equipo = " AND equipo_id = $equipo" if equipo_id else ""
        sql = (
            "SELECT time, equipo_id, posesion_pct, tiros_acumulados, pases_intervalo "
            "FROM estadisticas_partido "
            "WHERE partido_id = $partido AND time >= $desde AND time < $hasta"
            f"{filtro_equipo} "
            f"ORDER BY time, equipo_id LIMIT {int(limit)}"
        )
        params = {"partido": partido_id, "desde": desde, "hasta": hasta}
        if equipo_id:
            params["equipo"] = equipo_id
        return self.query_sql(sql, params)

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

    def query_sql(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL parametrizada contra la base temporal configurada.

        Solo los fallos de disponibilidad (conexión, timeout, 5xx, credenciales) dan
        'fuente no disponible'; una consulta rechazada (4xx) es un error de la aplicación.
        """
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
            "q": query,
            "params": params or {},
        }

        try:
            response = self.get_session().post(
                url, json=payload, headers=headers, timeout=settings.db_timeout_seconds
            )
        except requests.RequestException as e:
            logger.warning("Fallo de conexión con InfluxDB: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("InfluxDB", e) from e

        if response.status_code in (401, 403) or response.status_code >= 500:
            logger.warning("InfluxDB respondió %s", response.status_code)
            raise DatabaseUnavailableError("InfluxDB")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session is not None:
            self._session.close()
            self._session = None


influx_adapter = InfluxAdapter()
