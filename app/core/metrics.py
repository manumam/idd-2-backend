"""Métricas Prometheus de la API."""

import threading
import time
from typing import Callable, Iterable

# encontrado en documentación de prometheus_client
from prometheus_client import Counter, Histogram
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

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

dependencia_seconds = Histogram(
    "api_dependencia_seconds",
    "Duración de cada operación de adaptador por fuente y operación.",
    ["fuente", "operacion"],
)

dependencia_errores_total = Counter(
    "api_dependencia_errores_total",
    "Fallas de operaciones de adaptador por fuente y categoría.",
    ["fuente", "categoria"],
)


def route_template(scope: dict) -> str:
    route = scope.get("route")
    return getattr(route, "path", RUTA_SIN_COINCIDENCIA)


def record_request(ruta: str, metodo: str, status: int, elapsed_seconds: float) -> None:
    http_requests_total.labels(ruta=ruta, metodo=metodo, status=str(status)).inc()
    latency_seconds.labels(ruta=ruta).observe(elapsed_seconds)


def record_cache(funcionalidad: str, resultado: str) -> None:
    cache_total.labels(funcionalidad=funcionalidad, resultado=resultado).inc()


def record_dependencia(fuente: str, operacion: str, elapsed_seconds: float) -> None:
    dependencia_seconds.labels(fuente=fuente, operacion=operacion).observe(elapsed_seconds)


def record_dependencia_error(fuente: str, categoria: str) -> None:
    dependencia_errores_total.labels(fuente=fuente, categoria=categoria).inc()


class EstadoFuentesCollector(Collector):
    def __init__(self, evaluar: Callable[[tuple[str, ...]], dict], fuentes: Iterable[str],
                 intervalo_segundos: float, reloj: Callable[[], float] = time.monotonic):
        self._evaluar = evaluar
        self._fuentes = tuple(fuentes)
        self._intervalo_segundos = intervalo_segundos
        self._reloj = reloj
        self._estados: dict[str, str] = {}
        self._evaluado_en: dict[str, float] = {}
        self._lock = threading.Lock()

    def registrar(self, estados: dict) -> None:
        with self._lock:
            self._guardar(estados)

    def _guardar(self, estados: dict) -> None:
        ahora = self._reloj()
        for fuente, estado in estados.items():
            self._estados[fuente] = estado
            self._evaluado_en[fuente] = ahora

    def _vencidas(self) -> tuple[str, ...]:
        ahora = self._reloj()
        return tuple(f for f in self._fuentes
                     if ahora - self._evaluado_en.get(f, float("-inf")) >= self._intervalo_segundos)

    def _familia(self) -> GaugeMetricFamily:
        return GaugeMetricFamily("api_dependencia_up", "1 si la fuente respondió el último ping, 0 si no.",
                                 labels=["fuente"])

    def describe(self):
        yield self._familia()

    def collect(self):
        with self._lock:
            vencidas = self._vencidas()
            if vencidas:
                self._guardar(self._evaluar(vencidas))
            estados = dict(self._estados)
        familia = self._familia()
        for fuente in self._fuentes:
            if fuente in estados:
                familia.add_metric([fuente], 1.0 if estados[fuente] == "up" else 0.0)
        yield familia
