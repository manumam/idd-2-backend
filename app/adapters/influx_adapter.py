"""Adaptador para InfluxDB 3 (Módulo Temporal: Estadísticas de Partidos).

Encapsula la API HTTP/SQL de InfluxDB 3 Core con lectura automática de tokens y timeouts (RF7, RNF5, RNF8).
"""

import os
import logging
from typing import Any, Dict, List, Optional
import requests

from app.adapters.base import BaseAdapter
from app.core.observability import observe
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

# encontrado en documentación de InfluxDB (SQL: floor, least)
# Misma celda que la materialización: LEAST lleva el borde lejano (x = 105, y = 68) a la última celda.
SQL_MUESTRAS_POR_CELDA = (
    "SELECT LEAST(FLOOR(x_m / $lado_m), $ultima_columna) AS columna, "
    "LEAST(FLOOR(y_m / $lado_m), $ultima_fila) AS fila, "
    "COUNT(*) AS muestras "
    "FROM tracking_jugador "
    "WHERE partido_id = $partido AND jugador_id = $jugador AND time >= $desde AND time < $hasta "
    "AND x_m BETWEEN 0 AND $largo_m AND y_m BETWEEN 0 AND $ancho_m "
    "GROUP BY columna, fila"
)

# El tiempo de cada punto es el comienzo de su ventana de un minuto.
SQL_OCUPACION_POR_CELDA = (
    "SELECT celda, SUM(muestras) AS muestras "
    "FROM ocupacion_jugador_minuto "
    "WHERE partido_id = $partido AND jugador_id = $jugador AND time >= $desde AND time < $hasta "
    "GROUP BY celda"
)


def _tabla_inexistente(error: DatabaseUnavailableError) -> bool:
    response = getattr(error.original_error, "response", None)
    if response is None or response.status_code != 400:
        return False
    texto = response.text or ""
    return "table" in texto and "not found" in texto


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

        if not settings.influx_token_file_enabled:
            return None

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
                    logger.debug("No se pudo leer token en %s: %s", path, e.__class__.__name__)
        return None

    def get_session(self) -> requests.Session:
        """Obtiene la sesión HTTP reutilizable."""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    @observe("InfluxDB")
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

    @observe("InfluxDB")
    def contar_muestras_por_celda(
        self, partido_id: str, jugador_id: str, desde: str, hasta: str, grilla: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Muestras crudas de un jugador por celda en [desde, hasta), desde la base en vivo."""
        params = dict(grilla, partido=partido_id, jugador=jugador_id, desde=desde, hasta=hasta)
        return self.query_sql(SQL_MUESTRAS_POR_CELDA, params, settings.influx_database_en_vivo)

    @observe("InfluxDB")
    def sumar_ocupacion_por_celda(self, partido_id: str, jugador_id: str, desde: str, hasta: str) -> List[Dict[str, Any]]:
        """Muestras materializadas de un jugador por celda, de las ventanas que empiezan en [desde, hasta)."""
        params = {"partido": partido_id, "jugador": jugador_id, "desde": desde, "hasta": hasta}
        try:
            return self.query_sql(SQL_OCUPACION_POR_CELDA, params, settings.influx_database)
        except DatabaseUnavailableError as error:
            # Antes de la primera materialización la tabla no existe: no hay histórico, no es una falla.
            if _tabla_inexistente(error):
                return []
            raise

    @observe("InfluxDB")
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
            error = requests.HTTPError(response=response)
            raise DatabaseUnavailableError("InfluxDB", error) from error
        except requests.RequestException as e:
            logger.warning("Fallo en ping InfluxDB: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("InfluxDB", e)

    def query_sql(
        self, query: str, params: Optional[Dict[str, Any]] = None, database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL parametrizada contra una base temporal configurada.

        `database` debe ser una de las bases de settings; por defecto, INFLUX_DATABASE.

        Solo los fallos de disponibilidad (conexión, timeout, 5xx, credenciales) dan
        'fuente no disponible'; una consulta rechazada (4xx) es un error de la aplicación.
        """
        database = database or settings.influx_database
        if database not in (settings.influx_database, settings.influx_database_en_vivo):
            raise ValueError("Base de InfluxDB no configurada")

        token = self._resolve_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{settings.influx_url.rstrip('/')}/api/v3/query_sql"
        payload = {
            "db": database,
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

        if response.status_code >= 400:
            logger.warning("InfluxDB respondió %s", response.status_code)
            error = requests.HTTPError(response=response)
            raise DatabaseUnavailableError("InfluxDB", error) from error
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        if self._session is not None:
            self._session.close()
            self._session = None


influx_adapter = InfluxAdapter()
