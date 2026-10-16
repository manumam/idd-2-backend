"""Excepciones de dominio y de infraestructura.

Cumple con RF11, RF12, RNF4, RNF9:
- Define un formato unificado para fallas de dependencias.
- No expone credenciales, sentencias internas ni datos técnicos sensibles al cliente.
"""

from typing import Optional


class BaseAppException(Exception):
    """Excepción base para todos los errores de la aplicación."""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DatabaseUnavailableError(BaseAppException):
    """Lanzada cuando una base NoSQL está caída o no responde en tiempo y forma.

    Mapea a HTTP 503 (Service Unavailable) y encapsula el error nativo en logs
    sin mostrarlo en el mensaje público hacia el cliente (RF12 / RNF9).
    """

    def __init__(self, source: str, original_error: Optional[Exception] = None):
        self.source = source
        self.original_error = original_error
        code = f"{source.upper()}_UNAVAILABLE"
        message = f"El servicio de datos '{source}' no se encuentra disponible temporalmente."
        super().__init__(code=code, message=message, status_code=503)


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
