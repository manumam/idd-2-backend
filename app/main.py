"""Punto de entrada de la API REST del Fixture 2030."""

import logging

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.handlers import register_handlers
from app.core.request_context import request_context_middleware
from app.routes import equipos, health, sesiones
from app.schemas.errors import ErrorResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Fixture 2030 API",
    version="0.1.0",
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
                operation["responses"].pop("422", None)
        for name in ("HTTPValidationError", "ValidationError"):
            schema.get("components", {}).get("schemas", {}).pop(name, None)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
