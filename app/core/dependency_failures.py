"""Clasificación por tipos/códigos del driver; nunca por mensajes con secretos."""
import socket

from neo4j.exceptions import AuthError, ClientError, Neo4jError
from pymongo.errors import ExecutionTimeout, NetworkTimeout, OperationFailure, ServerSelectionTimeoutError
from redis.exceptions import AuthenticationError, AuthorizationError, TimeoutError as RedisTimeout
import requests


def classify_failure(error: Exception | None) -> str:
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        category = getattr(error, 'category', None)
        if category and hasattr(error, 'original_error'):
            return category
        if isinstance(error, (TimeoutError, requests.Timeout, RedisTimeout, ExecutionTimeout, NetworkTimeout, ServerSelectionTimeoutError)):
            return 'timeout'
        # AuthenticationError may inherit from a broader connection exception.
        if isinstance(error, (AuthenticationError, AuthError)):
            return 'authentication'
        if isinstance(error, AuthorizationError):
            return 'authorization'
        if isinstance(error, OperationFailure):
            return {18: 'authentication', 13: 'authorization', 26: 'context'}.get(error.code, 'query')
        if isinstance(error, Neo4jError):
            code = error.code or ''
            if code in ('Neo.ClientError.Security.Unauthorized', 'Neo.ClientError.Security.AuthenticationRateLimit'):
                return 'authentication'
            if code in ('Neo.ClientError.Security.Forbidden', 'Neo.ClientError.Security.AuthorizationExpired'):
                return 'authorization'
            if code in ('Neo.ClientError.Database.DatabaseNotFound', 'Neo.ClientError.Database.DatabaseUnavailable'):
                return 'context'
            if 'TimedOut' in code:
                return 'timeout'
            if isinstance(error, ClientError):
                return 'query'
        if isinstance(error, requests.HTTPError) and error.response is not None:
            status = error.response.status_code
            if status in (401, 403, 404):
                return {401: 'authentication', 403: 'authorization', 404: 'context'}[status]
            if 400 <= status < 500:
                return 'query'
        if isinstance(error, socket.gaierror):
            return 'resolution'
        if isinstance(error, ConnectionRefusedError):
            return 'connection_refused'
        error = getattr(error, 'original_error', None) or error.__cause__ or error.__context__
    return 'unavailable'
