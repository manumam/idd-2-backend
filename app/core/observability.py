"""Logs de operaciones de adaptadores sin consultas, parámetros ni mensajes del driver."""

import logging
import time
from functools import wraps

from app.core.request_context import current_request_id

logger = logging.getLogger("fixture2030.adapters")


def observe(source):
    def decorate(operation):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            start = time.perf_counter()
            result = "ok"
            try:
                return operation(*args, **kwargs)
            except Exception:
                result = "error"
                raise
            finally:
                logger.info("request_id=%s dependency=%s operation=%s result=%s duration_ms=%.1f",
                            current_request_id(), source, operation.__name__, result,
                            (time.perf_counter() - start) * 1000)
        return wrapped
    return decorate
