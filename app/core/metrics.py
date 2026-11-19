"""Métricas Prometheus de la API."""

# encontrado en documentación de prometheus_client
from prometheus_client import Counter, Histogram

METRICS_PATH = "/metrics"
RUTA_SIN_COINCIDENCIA = "sin_ruta"

http_requests_total = Counter(
    "api_http_requests_total",
    "Requests HTTP atendidos por ruta, método y estado.",
    ["ruta", "metodo", "status"],
)

latency_seconds = Histogram(
    "api_latency_seconds",
    "Duración de los requests HTTP por ruta.",
    ["ruta"],
    # 0.1 s es el umbral del SLO P95 < 100 ms (arquitectura del sistema).
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


# Valores acotados: funcionalidad sale de un conjunto fijo, nunca de claves ni códigos.
cache_total = Counter(
    "api_cache_total",
    "Lecturas de caché por funcionalidad y resultado (hit, miss o error con fallback a MongoDB).",
    ["funcionalidad", "resultado"],
)


def route_template(scope: dict) -> str:
    route = scope.get("route")
    return getattr(route, "path", RUTA_SIN_COINCIDENCIA)


def record_request(ruta: str, metodo: str, status: int, elapsed_seconds: float) -> None:
    http_requests_total.labels(ruta=ruta, metodo=metodo, status=str(status)).inc()
    latency_seconds.labels(ruta=ruta).observe(elapsed_seconds)


def record_cache(funcionalidad: str, resultado: str) -> None:
    cache_total.labels(funcionalidad=funcionalidad, resultado=resultado).inc()
