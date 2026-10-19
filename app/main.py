"""Punto de entrada de la API REST del Fixture 2030."""

import logging
from contextlib import asynccontextmanager

from app.services.health_service import FUENTES

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.handlers import register_handlers
from app.core.request_context import request_context_middleware
from app.routes import comentarios, equipos, estadisticas, health, partidos, sesiones
from app.schemas.errors import ErrorResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

@asynccontextmanager
async def lifespan(app):
    yield
    for adapter in FUENTES.values():
        try:
            adapter.close()
        except Exception as exc:
            logging.getLogger(__name__).warning("Cierre de adaptador: %s", type(exc).__name__)


app = FastAPI(
    lifespan=lifespan,
    title="Fixture 2030 API",
    version="1.0.0",
    description="API REST integrada del Fixture Mundial 2030 (Hito 10).",
    servers=[{"url": "http://localhost:8000", "description": "Local"}],
    responses={
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)

app.middleware("http")(request_context_middleware)
register_handlers(app)
app.include_router(health.router)
app.include_router(equipos.router)
app.include_router(sesiones.router)
app.include_router(partidos.router)
app.include_router(estadisticas.router)
app.include_router(comentarios.router)


def custom_openapi():
    """Quita el 422 que FastAPI agrega por defecto: la API responde 400 ante entradas inválidas."""
    if app.openapi_schema is None:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            servers=app.servers,
            routes=app.routes,
        )
        for path in schema["paths"].values():
            for operation in path.values():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                operation["responses"].pop("422", None)
                for response in operation["responses"].values():
                    response.setdefault("headers", {})["X-Request-Id"] = {
                        "description": "Identificador de correlación", "schema": {"type": "string"}
                    }
        for name in ("HTTPValidationError", "ValidationError"):
            schema.get("components", {}).get("schemas", {}).pop(name, None)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
