"""Caso de uso 12: estado de las dependencias."""

from concurrent.futures import ThreadPoolExecutor

from app.adapters import (
    cassandra_adapter,
    influx_adapter,
    iris_adapter,
    mongo_adapter,
    neo4j_adapter,
    redis_adapter,
)
from app.core.exceptions import DatabaseUnavailableError

FUENTES = {
    "mongodb": mongo_adapter,
    "neo4j": neo4j_adapter,
    "cassandra": cassandra_adapter,
    "redis": redis_adapter,
    "influxdb": influx_adapter,
    "iris": iris_adapter,
}


def _estado(adapter) -> str:
    try:
        return "up" if adapter.ping() else "down"
    except DatabaseUnavailableError:
        return "down"


def estado_dependencias() -> dict:
    """Consulta las fuentes en paralelo para que una caída no sume los timeouts."""
    with ThreadPoolExecutor(max_workers=len(FUENTES)) as pool:
        futuros = {nombre: pool.submit(_estado, a) for nombre, a in FUENTES.items()}
    return {nombre: f.result() for nombre, f in futuros.items()}
