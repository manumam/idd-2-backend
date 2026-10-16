"""Punto de entrada de la API REST del Fixture 2030."""

import logging

from fastapi import FastAPI

from app.core.handlers import register_handlers
from app.core.request_context import request_context_middleware
from app.routes import health
from app.schemas.errors import ErrorResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="Fixture 2030 API",
    version="0.1.0",
    description="API REST integrada del Fixture Mundial 2030 (Hito 10).",
    servers=[{"url": "http://localhost:8000", "description": "Local"}],
    responses={
        400: {"model": ErrorResponse, "description": "Parámetro o cuerpo inválido"},
        500: {"model": ErrorResponse, "description": "Error interno"},
    },
)

app.middleware("http")(request_context_middleware)
register_handlers(app)
app.include_router(health.router)
