"""Módulo de acceso central a los adaptadores del sistema."""

from app.adapters.mongo_adapter import mongo_adapter
from app.adapters.redis_adapter import redis_adapter
from app.adapters.influx_adapter import influx_adapter

__all__ = [
    "mongo_adapter",
    "redis_adapter",
    "influx_adapter",
]
