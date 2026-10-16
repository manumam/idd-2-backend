"""Adaptador para Neo4j (Módulo de Grafos: Partidos y Eventos).

Encapsula el driver Bolt oficial y sesiones para consultas Cypher parametrizadas (RF4, RNF5).
"""

import logging
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver, Query
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired, TransientError

from app.adapters.base import BaseAdapter
from app.core.observability import observe
from app.config.settings import settings
from app.core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

# Consultas fijas y parametrizadas: el cliente nunca aporta texto Cypher.
_CYPHER_PARTIDO = """
MATCH (p:Partido {id: $id})
RETURN p.id AS id, p.fase AS fase, p.grupo AS grupo, p.fecha AS fecha
"""

_CYPHER_SEDE_DE_PARTIDO = """
MATCH (:Partido {id: $id})-[:SE_DISPUTA_EN]->(s:Sede)
RETURN s.id AS id, s.nombre AS nombre, s.ciudad AS ciudad
"""

_CYPHER_EQUIPOS_DE_PARTIDO = """
MATCH (e:Equipo)-[r:PARTICIPA_EN]->(:Partido {id: $id})
RETURN e.id AS id, e.nombre AS nombre, r.condicion AS condicion
"""

_CYPHER_EVENTOS = """
MATCH (ev:Evento)-[:OCURRE_EN]->(:Partido {id: $id})
RETURN ev.id AS id, ev.tipo AS tipo, ev.minuto AS minuto
ORDER BY minuto, id
LIMIT $limit
"""

_CYPHER_PROTAGONISTAS = """
MATCH (j:Jugador)-[r:PROTAGONIZA]->(ev:Evento)
WHERE ev.id IN $evento_ids
RETURN ev.id AS evento_id, j.id AS id, j.nombre AS nombre, j.apellido AS apellido, r.rol AS rol
ORDER BY evento_id, rol, id
"""

_CYPHER_SEDE = "MATCH (s:Sede {id: $id}) RETURN s.id AS id"

_CYPHER_GOLEADORES = """
MATCH (s:Sede {id: $sede})<-[:SE_DISPUTA_EN]-(p:Partido)<-[:OCURRE_EN]-(gol:Evento {tipo: 'Gol'})
      <-[:PROTAGONIZA {rol: 'autor'}]-(j:Jugador)-[:PERTENECE_A]->(e:Equipo {confederacion: $confederacion})
RETURN j.id AS jugador_id, j.nombre AS jugador_nombre, j.apellido AS jugador_apellido,
       e.id AS equipo_id, e.nombre AS equipo_nombre, p.id AS partido, gol.minuto AS minuto
ORDER BY partido, minuto, jugador_id
LIMIT $limit
"""


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
                    connection_acquisition_timeout=settings.db_timeout_seconds,
                    max_transaction_retry_time=0,
                )
            except Exception as e:
                logger.error("Error al inicializar driver Neo4j: %s", e.__class__.__name__)
                raise DatabaseUnavailableError("Neo4j", e)
        return self._driver

    def _run(self, cypher: str, **params: Any) -> List[Dict[str, Any]]:
        """Ejecuta una consulta de lectura y traduce los errores del driver a 'fuente no disponible'."""
        try:
            with self.get_driver().session(database=settings.neo4j_database) as session:
                return [registro.data() for registro in session.run(Query(cypher, timeout=settings.db_timeout_seconds), params)]
        except (ServiceUnavailable, SessionExpired, AuthError, TransientError) as e:
            logger.warning("Fallo en consulta Neo4j: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("Neo4j", e) from e

    @observe("Neo4j")
    def find_partido(self, partido_id: str) -> Optional[Dict[str, Any]]:
        """Ficha del partido con sede y equipos; None si no existe."""
        filas = self._run(_CYPHER_PARTIDO, id=partido_id)
        if not filas:
            return None
        partido = filas[0]
        partido["fecha"] = partido["fecha"].iso_format() if partido["fecha"] is not None else None
        sedes = self._run(_CYPHER_SEDE_DE_PARTIDO, id=partido_id)
        partido["sede"] = sedes[0] if sedes else None
        for equipo in self._run(_CYPHER_EQUIPOS_DE_PARTIDO, id=partido_id):
            if equipo["condicion"] in ("Local", "Visitante"):
                partido[equipo["condicion"].lower()] = {"id": equipo["id"], "nombre": equipo["nombre"]}
        return partido

    @observe("Neo4j")
    def find_eventos(self, partido_id: str, limit: int) -> Optional[List[Dict[str, Any]]]:
        """Eventos del partido por minuto; None si el partido no existe, lista vacía si no tiene eventos."""
        if not self._run(_CYPHER_PARTIDO, id=partido_id):
            return None
        eventos = self._run(_CYPHER_EVENTOS, id=partido_id, limit=limit)
        for evento in eventos:
            evento["protagonistas"] = []
        por_id = {evento["id"]: evento for evento in eventos}
        if por_id:
            for fila in self._run(_CYPHER_PROTAGONISTAS, evento_ids=list(por_id)):
                por_id[fila["evento_id"]]["protagonistas"].append(
                    {"id": fila["id"], "nombre": f"{fila['nombre']} {fila['apellido']}", "rol": fila["rol"]}
                )
        return eventos

    @observe("Neo4j")
    def sede_existe(self, sede_id: str) -> bool:
        return bool(self._run(_CYPHER_SEDE, id=sede_id))

    @observe("Neo4j")
    def find_goleadores(self, sede_id: str, confederacion: str, limit: int) -> List[Dict[str, Any]]:
        """Goles de jugadores de una confederación en los partidos de una sede."""
        goles = self._run(_CYPHER_GOLEADORES, sede=sede_id, confederacion=confederacion, limit=limit)
        for gol in goles:
            gol["jugador_nombre"] = f"{gol['jugador_nombre']} {gol.pop('jugador_apellido')}"
        return goles

    @observe("Neo4j")
    def ping(self) -> bool:
        """Verifica conectividad y autenticación contra Neo4j."""
        try:
            driver = self.get_driver()
            driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning("Fallo en ping Neo4j: %s", e.__class__.__name__)
            raise DatabaseUnavailableError("Neo4j", e)

    def close(self) -> None:
        """Cierra el driver de Neo4j."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


neo4j_adapter = Neo4jAdapter()
