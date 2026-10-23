"""Traducción de excepciones a respuestas de error con formato único.

El detalle técnico va solo a los logs; el cliente recibe código y mensaje seguros.
"""

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.exceptions import BaseAppException, DatabaseUnavailableError
from app.core.request_context import current_request_id

logger = logging.getLogger("fixture2030.errors")


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "requestId": current_request_id()},
    )


async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
    if isinstance(exc, DatabaseUnavailableError):
        logger.warning(
            "request_id=%s dependency=%s category=%s error=%s",
            current_request_id(), exc.source, exc.category, type(exc.original_error).__name__,
        )
    return _error(exc.status_code, exc.code, exc.message)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    campos = sorted({".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()})
    return _error(400, "VALIDACION_INVALIDA", "Parámetros inválidos: " + ", ".join(campos) + ".")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Rutas o métodos inexistentes: mismo formato de error que el resto de la API
    if exc.status_code == 404:
        return _error(404, "RUTA_NO_ENCONTRADA", "La ruta solicitada no existe.")
    if exc.status_code == 405:
        return _error(405, "METODO_NO_PERMITIDO", "Método no permitido para esta ruta.")
    return _error(exc.status_code, "ERROR_HTTP", "Solicitud no válida.")


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BaseAppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
