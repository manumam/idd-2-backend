#!/usr/bin/env python3
"""Diagnóstico no destructivo; no imprime excepciones ni URI con credenciales."""
import argparse
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config.settings import settings
from app.services.health_service import FUENTES
import requests

ROUTES = {
    'mongodb': ['/equipos/ARG', '/jugadores?equipo=ARG&limit=2', '/jugadores/ARG-10'],
    'neo4j': ['/partidos/P-001', '/partidos/P-001/eventos?limit=2', '/sedes/S-04/goleadores?confederacion=CONMEBOL&limit=2'],
    'redis': ['/sesiones/SES-DEMO'],
    'influxdb': ['/partidos/P-001/estadisticas?desde=2030-06-24T20:00:00Z&hasta=2030-06-24T20:05:00Z'],
}


def target(source):
    if source == 'redis':
        return settings.redis_host, settings.redis_port
    url, default = {
        'mongodb': (settings.mongo_uri, 27017),
        'neo4j': (settings.neo4j_uri, 7687),
        'influxdb': (settings.influx_url, 8181),
    }[source]
    parsed = urlsplit(url)
    return parsed.hostname, parsed.port or default


def read_minimum(source):
    adapter = FUENTES[source]
    if source == 'mongodb':
        db = adapter.db
        if 'equipos' not in db.list_collection_names():
            return {'estado': 'degradado', 'diagnostico': 'coleccion_equipos_ausente'}
        found = db.equipos.find_one({'_id': 'ARG'}, {'_id': 1})
    elif source == 'neo4j':
        found = adapter.find_partido('P-001')
    elif source == 'redis':
        found = adapter.get_sesion('SES-DEMO')
        ttl = adapter.client.ttl('sesion:SES-DEMO')
        return {'estado': 'disponible', 'resultado': 'clave_presente' if found else 'clave_ausente_o_expirada', 'ttl': ttl}
    else:
        found = adapter.find_estadisticas('P-001', '2030-06-24T20:00:00Z', '2030-06-24T20:05:00Z', None, 2)
    return {'estado': 'disponible', 'resultado': 'datos_presentes' if found else 'sin_datos'}


def failure(exc):
    from app.core.dependency_failures import classify_failure
    return {
        'resolution': 'host_no_resuelto', 'connection_refused': 'conexion_rechazada',
        'timeout': 'timeout', 'authentication': 'autenticacion_rechazada',
        'authorization': 'permiso_denegado', 'context': 'contexto_no_disponible',
        'query': 'consulta_invalida',
    }.get(classify_failure(exc), 'fallo_no_clasificado')


def run_probe(source, layer, operation):
    started = time.perf_counter()
    row = dict(producto=source, capa=layer, fecha=datetime.now(timezone.utc).isoformat())
    try:
        result = operation()
        row.update(result if isinstance(result, dict) else {'estado': 'no_disponible' if result is False else 'disponible'})
    except Exception as exc:
        row.update(estado='no_disponible', diagnostico=failure(exc), siguiente_paso='Revisar esta capa con el cliente del producto; no inferir fallas de capas posteriores.')
    row['duracion_ms'] = round((time.perf_counter() - started) * 1000, 2)
    return row


def tcp(host, port):
    with socket.create_connection((host, port), timeout=settings.db_timeout_seconds):
        pass


def api_probe(base, path):
    request_id = 'hito11-' + uuid4().hex
    response = requests.get(base + path, headers={'X-Request-Id': request_id}, timeout=settings.db_timeout_seconds + 1)
    result = dict(estado='disponible' if response.status_code == 200 else 'degradado', metodo='GET', path=path,
                  status_http=response.status_code, request_id=response.headers.get('X-Request-Id'), correlacion_esperada=request_id)
    if path in ('/live', '/health', '/ready'):
        body = response.json()
        result['sistema'] = {key: body[key] for key in ('estado', 'listo') if key in body}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modo', choices=['completo', 'configuracion', 'tcp', 'clientes', 'api'], default='completo')
    parser.add_argument('--producto', choices=list(FUENTES))
    parser.add_argument('--base-url', default='http://127.0.0.1:18000')
    parser.add_argument('--salida', type=Path)
    args = parser.parse_args()
    rows = []
    sources = [args.producto] if args.producto else list(FUENTES)
    try:
        for source in sources:
            if args.modo in ('completo', 'configuracion', 'tcp'):
                config = run_probe(source, 'configuracion', lambda: dict(estado='disponible', host=target(source)[0], puerto=target(source)[1]))
                rows.append(config)
                if config['estado'] != 'disponible':
                    continue
                host, port = target(source)
                rows.append(run_probe(source, 'resolucion', lambda: socket.getaddrinfo(host, port)))
                if args.modo != 'configuracion':
                    rows.append(run_probe(source, 'tcp', lambda: tcp(host, port)))
            if args.modo in ('completo', 'clientes'):
                rows.append(run_probe(source, 'protocolo', FUENTES[source].ping))
                rows.append(run_probe(source, 'contexto_y_lectura', lambda: read_minimum(source)))
            if args.modo in ('completo', 'api'):
                for path in ROUTES[source]:
                    rows.append(run_probe(source, 'api', lambda: api_probe(args.base_url.rstrip('/'), path)))
    finally:
        for source in sources:
            FUENTES[source].close()
    report = dict(origen='proceso_python_en_host', resultados=rows,
                  limitaciones=['Identidad, autorizacion y contexto se verifican conjuntamente con la lectura; no se certifican por separado.',
                                'Laboratorio sin autenticacion: no evalua rechazo de credenciales.',
                                'IRIS y Cassandra fuera del alcance por decision del equipo.'])
    output = json.dumps(report, indent=2, ensure_ascii=False)
    print(output)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(output + '\n')
    return int(any(row['estado'] != 'disponible' for row in rows))


if __name__ == '__main__':
    sys.exit(main())
