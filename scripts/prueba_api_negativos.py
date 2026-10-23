#!/usr/bin/env python3
"""Casos HTTP negativos reales y simulaciones ASGI etiquetadas, sin rutas de prueba en producción."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from fastapi.testclient import TestClient
from redis.exceptions import AuthenticationError, AuthorizationError, TimeoutError as RedisTimeout
from pymongo.errors import OperationFailure
from app.main import app
from app.adapters import mongo_adapter, redis_adapter


@contextmanager
def capture_logs():
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    logging.getLogger().addHandler(handler)
    try:
        yield buffer
    finally:
        logging.getLogger().removeHandler(handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18000')
    parser.add_argument('--salida', type=Path, default=Path('docs/hito_11/evidencia/api_negativos.json'))
    args = parser.parse_args()
    rows = []

    def execute(client, case, path, expected, origin, dependency, expected_code=None, empty=False):
        request_id = 'hito11-neg-' + uuid4().hex
        start = time.perf_counter()
        response = client.get(path, headers={'X-Request-Id': request_id})
        body = response.json()
        row = dict(caso=case, origen=origin, dependencia=dependency, metodo='GET', path=path,
                   fecha=datetime.now(timezone.utc).isoformat(), status_http=response.status_code,
                   esperado=expected, request_id=response.headers.get('X-Request-Id'),
                   duracion_ms=round((time.perf_counter()-start)*1000, 2), codigo=body.get('code'))
        row['correcto'] = response.status_code == expected and row['request_id'] == request_id
        if expected_code:
            row['correcto'] &= body.get('code') == expected_code and body.get('requestId') == request_id
        if empty:
            row['items'] = len(body.get('items', []))
            row['correcto'] &= body.get('items') == []
        rows.append(row)

    class HttpClient:
        def get(self, path, **kwargs):
            return requests.get(args.base_url.rstrip('/') + path, timeout=8, **kwargs)

    real = HttpClient()
    execute(real, 'recurso_inexistente', '/equipos/ZZZ', 404, 'HTTP_TCP_motor_real', 'mongodb', 'EQUIPO_NO_ENCONTRADO')
    execute(real, 'lista_vacia_valida', '/jugadores?equipo=ZZZ', 200, 'HTTP_TCP_motor_real', 'mongodb', empty=True)
    execute(real, 'validacion', '/jugadores?equipo=ARG&limit=0', 400, 'HTTP_TCP', 'ninguna', 'VALIDACION_INVALIDA')
    execute(real, 'ruta_inexistente', '/ruta-inexistente-hito11', 404, 'HTTP_TCP', 'ninguna', 'RUTA_NO_ENCONTRADA')
    # Retener el socket reservado sin listen garantiza un puerto sin API sin tocar el servidor real.
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
        started = time.perf_counter()
        try:
            requests.get(f'http://127.0.0.1:{port}/health', timeout=1)
            refused = False
        except requests.ConnectionError:
            refused = True
        rows.append(dict(caso='api_inaccesible', origen='HTTP_TCP_puerto_sin_listener', correcto=refused,
                         fecha=datetime.now(timezone.utc).isoformat(), status_http=None, request_id=None,
                         duracion_ms=round((time.perf_counter()-started)*1000, 2)))

    # Inyección en el límite del driver: pasa por adaptador, servicio, handler y middleware reales.
    simulations = [
        ('timeout', redis_adapter, 'get_client', RedisTimeout('dato-sensible'), '/sesiones/SES-DEMO', 504, 'REDIS_TIMEOUT', 'redis'),
        ('autenticacion', redis_adapter, 'get_client', AuthenticationError('dato-sensible'), '/sesiones/SES-DEMO', 503, 'REDIS_AUTHENTICATION_FAILED', 'redis'),
        ('autorizacion', redis_adapter, 'get_client', AuthorizationError('dato-sensible'), '/sesiones/SES-DEMO', 503, 'REDIS_ACCESS_DENIED', 'redis'),
        ('contexto', mongo_adapter, 'connect', OperationFailure('dato-sensible', code=26), '/equipos/ARG', 503, 'MONGODB_CONTEXT_UNAVAILABLE', 'mongodb'),
        ('consulta_invalida', mongo_adapter, 'connect', OperationFailure('dato-sensible', code=2), '/equipos/ARG', 500, 'MONGODB_QUERY_FAILED', 'mongodb'),
        ('error_interno', mongo_adapter, 'connect', RuntimeError('dato-sensible'), '/equipos/ARG', 500, 'ERROR_INTERNO', 'mongodb'),
    ]
    with capture_logs() as logs:
        with TestClient(app, raise_server_exceptions=False) as client:
            for case, adapter, method, error, path, status, code, dependency in simulations:
                with patch.object(adapter, method, side_effect=error):
                    execute(client, case, path, status, 'ASGI_simulacion_driver', dependency, code)
        safe_logs = '\n'.join(line for line in logs.getvalue().splitlines() if 'request_id=hito11-neg-' in line)
    report = dict(resultados=rows, limitaciones=['Autenticacion, permisos, contexto, timeout e interno se simulan; no certifican configuracion real de esos escenarios.', 'Los logs TCP reales deben capturarse desde el proceso Uvicorn.'])
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if 'dato-sensible' in serialized + safe_logs:
        raise RuntimeError('La salida contiene datos que deben redactarse')
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(serialized + '\n')
    args.salida.with_suffix('.log').write_text(safe_logs + '\n')
    for row in rows:
        print(row['caso'], row.get('status_http'), 'OK' if row['correcto'] else 'FALLO')
    return int(not all(row['correcto'] for row in rows))


if __name__ == '__main__':
    sys.exit(main())
