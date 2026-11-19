"""Caso de uso 12: estado de las dependencias."""

from concurrent.futures import ThreadPoolExecutor

from prometheus_client import REGISTRY

from app.adapters import influx_adapter, mongo_adapter, redis_adapter
from app.core.metrics import EstadoFuentesCollector

FUENTES = {
    "mongodb": mongo_adapter,
    "redis": redis_adapter,
    "influxdb": influx_adapter,
}

FUENTES_HEALTH = tuple(FUENTES)

# Redis es caché opcional: si cae, la API sigue respondiendo desde MongoDB.
FUENTES_ESENCIALES = ("mongodb", "influxdb")

# api_dependencia_up reutiliza /health y /ready; el scrape solo hace ping si el último
# resultado tiene más de 15 s (intervalo de scrape), para no generar una tormenta de conexiones.
INTERVALO_ESTADO_SEGUNDOS = 15


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


estado_fuentes = EstadoFuentesCollector(_consultar, FUENTES_HEALTH, INTERVALO_ESTADO_SEGUNDOS)
REGISTRY.register(estado_fuentes)


def estado_dependencias() -> dict:
    estados = _consultar(FUENTES_HEALTH)
    estado_fuentes.registrar(estados)
    return estados


def estado_readiness() -> tuple[dict, bool]:
    estados = _consultar(FUENTES_ESENCIALES)
    estado_fuentes.registrar(estados)
    return estados, all(estado == "up" for estado in estados.values())
