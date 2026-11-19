"""Logs de operaciones de adaptadores sin consultas, parámetros ni mensajes del driver."""

import logging
import time
from functools import wraps

from app.core.dependency_failures import classify_failure
from app.core.metrics import dependencia_en_curso, record_dependencia, record_dependencia_error
from app.core.request_context import current_request_id

logger = logging.getLogger("fixture2030.adapters")


def observe(source):
    fuente = source.lower()

    def decorate(operation):
        @wraps(operation)
        def wrapped(*args, **kwargs):
            start = time.perf_counter()
            result = "ok"
            en_curso = dependencia_en_curso.labels(fuente=fuente)
            en_curso.inc()
            try:
                return operation(*args, **kwargs)
            except Exception as exc:
                result = "error"
                record_dependencia_error(fuente, classify_failure(exc))
                raise
            finally:
                en_curso.dec()
                elapsed_seconds = time.perf_counter() - start
                record_dependencia(fuente, operation.__name__, elapsed_seconds)
                logger.info("request_id=%s dependency=%s operation=%s result=%s duration_ms=%.1f",
                            current_request_id(), source, operation.__name__, result,
                            elapsed_seconds * 1000)
        return wrapped
    return decorate
