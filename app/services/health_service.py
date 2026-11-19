"""Caso de uso 12: estado de las dependencias."""

from concurrent.futures import ThreadPoolExecutor

from app.adapters import (
    cassandra_adapter,
    iris_adapter,
    influx_adapter,
    mongo_adapter,
    neo4j_adapter,
    redis_adapter,
)

FUENTES = {
    "cassandra": cassandra_adapter,
    "iris": iris_adapter,
    "mongodb": mongo_adapter,
    "neo4j": neo4j_adapter,
    "redis": redis_adapter,
    "influxdb": influx_adapter,
}

FUENTES_HEALTH = ("mongodb", "redis", "influxdb")

# Redis es caché opcional: si cae, la API sigue respondiendo desde MongoDB.
FUENTES_ESENCIALES = ("mongodb", "influxdb")


def _estado(adapter) -> str:
    try:
        return "up" if adapter.ping() else "down"
    except Exception:
        # Un ping fallido no debe ocultar el estado de las demás fuentes.
        # Los adaptadores registran su tipo seguro; no publicar excepciones.
        return "down"


def _consultar(nombres: tuple[str, ...]) -> dict:
    """Consulta las fuentes en paralelo para que una caída no sume los timeouts."""
    with ThreadPoolExecutor(max_workers=len(nombres)) as pool:
        futuros = {nombre: pool.submit(_estado, FUENTES[nombre]) for nombre in nombres}
    return {nombre: f.result() for nombre, f in futuros.items()}


def estado_dependencias() -> dict:
    return _consultar(FUENTES_HEALTH)


def estado_readiness() -> tuple[dict, bool]:
    estados = _consultar(FUENTES_ESENCIALES)
    return estados, all(estado == "up" for estado in estados.values())
