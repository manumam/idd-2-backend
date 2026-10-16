"""Identificador de request y log por request."""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi.responses import JSONResponse
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-Id"
_VALID_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("fixture2030.access")


def current_request_id() -> str:
    return _request_id.get()


def _resolve_request_id(request: Request) -> str:
    """Usa el ID del cliente solo si tiene un formato seguro; si no, genera uno."""
    received = request.headers.get(REQUEST_ID_HEADER, "")
    return received if _VALID_ID.match(received) else str(uuid.uuid4())


async def request_context_middleware(request: Request, call_next):
    """Asigna request ID y registra método, ruta, estado y duración.

    También captura los errores inesperados acá: así el 500 conserva el request ID.
    """
    request_id = _resolve_request_id(request)
    token = _request_id.set(request_id)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s error inesperado", request_id)
            response = JSONResponse(
                status_code=500,
                content={
                    "code": "ERROR_INTERNO",
                    "message": "Error interno del servidor.",
                    "requestId": request_id,
                },
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id, request.method, request.url.path, response.status_code, elapsed_ms,
        )
        return response
    finally:
        _request_id.reset(token)
