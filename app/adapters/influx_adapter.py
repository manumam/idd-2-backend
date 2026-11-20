"""Adaptador para InfluxDB 3 (Módulo Temporal: Estadísticas de Partidos).

Encapsula la API HTTP/SQL de InfluxDB 3 Core con lectura automática de tokens y timeouts (RF7, RNF5, RNF8).
"""

import os
import logging
from typing import Any, Dict, Iterable, Iterator, List, Optional
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

LOTE_LINEAS = 10000
INTENTOS_POR_LOTE = 3
# Un lote de 10.000 líneas tarda más que una consulta puntual.
TIMEOUT_LOTE_SEG = 60


def en_lotes(lineas: Iterable[str], tamano: int = LOTE_LINEAS) -> Iterator[List[str]]:
    lote = []
    for linea in lineas:
        lote.append(linea)
        if len(lote) == tamano:
            yield lote
            lote = []
    if lote:
        yield lote


def _datos_mapa_inexistentes(error: DatabaseUnavailableError, tabla: str, database: str) -> bool:
    """Solo la ausencia identificada de datos opcionales equivale a un mapa vacío."""
    response = getattr(error.original_error, "response", None)
    if response is None:
        return False
    texto = response.text or ""
    if response.status_code == 400:
        return tabla in texto and "table" in texto and "not found" in texto
    if response.status_code == 404:
        try:
            mensaje = response.json().get("error", "")
        except (ValueError, AttributeError):
            return False
        return mensaje == f"query error: database not found: {database}"
    return False


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
        try:
            return self.query_sql(SQL_MUESTRAS_POR_CELDA, params, settings.influx_database_en_vivo)
        except DatabaseUnavailableError as error:
            if _datos_mapa_inexistentes(error, "tracking_jugador", settings.influx_database_en_vivo):
                return []
            raise

    @observe("InfluxDB")
    def sumar_ocupacion_por_celda(self, partido_id: str, jugador_id: str, desde: str, hasta: str) -> List[Dict[str, Any]]:
        """Muestras materializadas de un jugador por celda, de las ventanas que empiezan en [desde, hasta)."""
        params = {"partido": partido_id, "jugador": jugador_id, "desde": desde, "hasta": hasta}
        try:
            return self.query_sql(SQL_OCUPACION_POR_CELDA, params, settings.influx_database)
        except DatabaseUnavailableError as error:
            # Antes de la primera materialización la tabla no existe: no hay histórico, no es una falla.
            if _datos_mapa_inexistentes(error, "ocupacion_jugador_minuto", settings.influx_database):
                return []
            raise

    @observe("InfluxDB")
    def find_muestras(self, partido: str, desde: str, hasta: str):
        tablas = self.query_sql("SELECT table_name FROM information_schema.tables WHERE table_name = 'estadisticas_partido'")
        if not tablas:
            return []
        columnas = self.query_sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'estadisticas_partido'")
        duracion = "duracion_s" if any(c["column_name"] == "duracion_s" for c in columnas) else "NULL AS duracion_s"
        return self.query_sql(
            f"SELECT time, equipo_id, posesion_pct, tiros_acumulados, pases_intervalo, {duracion} "
            "FROM estadisticas_partido WHERE partido_id = $partido AND time >= $desde "
            "AND time <= $hasta ORDER BY time, equipo_id LIMIT 10001",
            {"partido": partido, "desde": desde, "hasta": hasta})

    def escribir_muestras(self, lineas: str) -> None:
        """Line protocol construido exclusivamente desde el plan validado."""
        self.escribir_lote(settings.influx_database, lineas.splitlines())

    def _validar_base_de_escritura(self, database: str) -> None:
        if database not in (settings.influx_database, settings.influx_database_en_vivo):
            raise ValueError("Base de InfluxDB no configurada")

    @observe("InfluxDB")
    def escribir_lote(self, database: str, lineas: List[str]) -> None:
        """Escribe un lote completo o ninguna línea (accept_partial=false), con reintentos acotados."""
        self._validar_base_de_escritura(database)
        headers = {"Content-Type": "text/plain; charset=utf-8"}
        token = self._resolve_token()
        if token:
            headers["Authorization"] = "Bearer " + token
        cuerpo = ("\n".join(lineas) + "\n").encode("utf-8")
        error = None
        for _ in range(INTENTOS_POR_LOTE):
            try:
                self.get_session().post(
                    f"{settings.influx_url.rstrip('/')}/api/v3/write_lp",
                    params={"db": database, "precision": "second", "accept_partial": "false", "no_sync": "false"},
                    headers=headers, data=cuerpo, timeout=TIMEOUT_LOTE_SEG).raise_for_status()
                return
            except requests.HTTPError as exc:
                error = exc
                if exc.response is not None and exc.response.status_code < 500:
                    # Líneas inválidas o credenciales rechazadas: reintentar no cambia la respuesta.
                    break
            except requests.RequestException as exc:
                error = exc
        logger.warning("InfluxDB rechazó un lote de %s líneas", len(lineas))
        raise DatabaseUnavailableError("InfluxDB", error) from error

    def escribir_lineas(self, database: str, lineas: Iterable[str]) -> int:
        """Escribe en lotes y devuelve las líneas rechazadas después de los reintentos."""
        self._validar_base_de_escritura(database)
        rechazadas = 0
        for lote in en_lotes(lineas):
            try:
                self.escribir_lote(database, lote)
            except DatabaseUnavailableError:
                rechazadas += len(lote)
        return rechazadas

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

    @observe("InfluxDB")
    def find_tracking_jugador(self, partido: str, jugador: str, equipo: str, desde: str, hasta: str):
        tablas = self.query_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'tracking_jugador'",
            database=settings.influx_tracking_database)
        if not tablas:
            return []
        return self.query_sql(
            "SELECT time, equipo_id, jugador_id, distancia_acum_m, velocidad_kmh "
            "FROM tracking_jugador WHERE partido_id = $partido AND jugador_id = $jugador "
            "AND equipo_id = $equipo AND time >= $desde AND time <= $hasta "
            "ORDER BY time LIMIT 14402",
            dict(partido=partido, jugador=jugador, equipo=equipo, desde=desde, hasta=hasta),
            database=settings.influx_tracking_database)

    def query_sql(
        self, query: str, params: Optional[Dict[str, Any]] = None, database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL parametrizada contra una base temporal configurada.

        `database` debe ser una de las bases de settings; por defecto, INFLUX_DATABASE.

        Solo los fallos de disponibilidad (conexión, timeout, 5xx, credenciales) dan
        'fuente no disponible'; una consulta rechazada (4xx) es un error de la aplicación.
        """
        database = database or settings.influx_database
        if database not in (settings.influx_database, settings.influx_database_en_vivo, settings.influx_tracking_database):
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
