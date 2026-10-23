"""Excepciones de dominio y de infraestructura.

Cumple con RF11, RF12, RNF4, RNF9:
- Define un formato unificado para fallas de dependencias.
- No expone credenciales, sentencias internas ni datos técnicos sensibles al cliente.
"""

from typing import Optional
from app.core.dependency_failures import classify_failure


class BaseAppException(Exception):
    """Excepción base para todos los errores de la aplicación."""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DatabaseUnavailableError(BaseAppException):
    """Lanzada cuando una base NoSQL está caída o no responde en tiempo y forma.

    Distingue timeout (504), configuración/disponibilidad (503) y consulta (500).
    Conserva el error nativo para clasificarlo sin publicar su mensaje.
    """

    def __init__(self, source: str, original_error: Optional[Exception] = None, *, category: str | None = None):
        self.source = source
        self.original_error = original_error
        self.category = category or classify_failure(original_error)
        suffix, status, message = {
            'timeout': ('TIMEOUT', 504, 'La dependencia excedió el tiempo de espera.'),
            'authentication': ('AUTHENTICATION_FAILED', 503, 'No se pudo autenticar ante la dependencia.'),
            'authorization': ('ACCESS_DENIED', 503, 'La identidad no tiene permiso para la operación.'),
            'context': ('CONTEXT_UNAVAILABLE', 503, 'El contexto de datos no está disponible.'),
            'query': ('QUERY_FAILED', 500, 'Error interno al consultar la dependencia.'),
        }.get(self.category, ('UNAVAILABLE', 503, f"El servicio de datos '{source}' no se encuentra disponible temporalmente."))
        super().__init__(code=f"{source.upper()}_{suffix}", message=message, status_code=status)


class ResourceNotFoundError(BaseAppException):
    """Lanzada cuando un recurso consultado no existe (404).

    El código lo define cada caso de uso (ej. EQUIPO_NO_ENCONTRADO).
    """

    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=404)


class InvalidRequestError(BaseAppException):
    """Lanzada cuando un parámetro o cuerpo es inválido (400), antes de consultar."""

    def __init__(self, message: str):
        super().__init__(code="VALIDACION_INVALIDA", message=message, status_code=400)
