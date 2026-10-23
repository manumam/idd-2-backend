#!/usr/bin/env python3
"""Reproduce el Hito 11 en el laboratorio aislado, conserva evidencia y volúmenes."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time

from dotenv import dotenv_values
import requests

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/hito_11/evidencia'
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.hito11.yaml')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--puerto-api', type=int, default=18001)
    args = parser.parse_args()
    # No cargar .env personal: todos los valores del laboratorio se fijan aquí.
    env = os.environ | {k: v for k, v in dotenv_values(ROOT / 'config/hito11.env.example').items() if v is not None}
    env['LIVE_MODULES'] = ''
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    def run(command, **kwargs):
        return subprocess.run(command, cwd=ROOT, env=env, check=True, **kwargs)
    with socket.socket() as port_check:
        port_check.bind(('127.0.0.1', args.puerto_api))
    run(COMPOSE + ['up', '-d'], timeout=180)
    for attempt in range(20):
        probe = subprocess.run([sys.executable, 'scripts/evaluar_conectividad.py', '--modo', 'clientes'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        # Contexto puede no existir antes de la carga: esperar solo el protocolo.
        if probe.returncode == 0:
            break
        pings = subprocess.run([sys.executable, 'scripts/verificar_conectividad.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        if pings.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Motores no disponibles dentro del plazo; ejecutar diagnostico por producto')
    run([sys.executable, 'scripts/preparar_lab.py', '--laboratorio-descartable', '--sources', 'mongodb,neo4j,redis,influxdb'], timeout=60)
    base = f'http://127.0.0.1:{args.puerto_api}'
    with (EVIDENCE / 'api_cierre.log').open('w') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(args.puerto_api)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for attempt in range(40):
                if server.poll() is not None:
                    raise RuntimeError('No inicio Uvicorn; revisar api_cierre.log')
                try:
                    if requests.get(base + '/live', timeout=1).status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError('API no disponible dentro del plazo')
            with (EVIDENCE / 'diagnostico_terminal.json').open('w') as output:
                run([sys.executable, 'scripts/evaluar_conectividad.py', '--base-url', base, '--salida', str(EVIDENCE / 'completo.json')], stdout=output, timeout=90)
            run([sys.executable, 'scripts/prueba_api_negativos.py', '--base-url', base], timeout=60)
            run([sys.executable, 'scripts/prueba_falla_redis.py', '--base-url', base], timeout=90)
            run([sys.executable, '-m', 'pytest', '-q', '--junitxml', str(EVIDENCE / 'suite.xml')], timeout=60)
            integration_env = env | {'LIVE_MODULES': 'mongodb,neo4j,redis,influxdb'}
            subprocess.run([sys.executable, '-m', 'pytest', 'tests/integration', '-q', '--junitxml', str(EVIDENCE / 'integracion.xml')], cwd=ROOT, env=integration_env, check=True, timeout=60)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    # Redactar identificadores de la notebook y rutas personales del JUnit.
    import xml.etree.ElementTree as ET
    for name in ('suite.xml', 'integracion.xml'):
        path = EVIDENCE / name
        tree = ET.parse(path)
        for suite in tree.iter('testsuite'):
            suite.set('hostname', 'laboratorio-local')
        for element in tree.iter():
            if element.text:
                element.text = element.text.replace(str(ROOT), '<repo>')
        tree.write(path, encoding='utf-8', xml_declaration=True)
    versions = dict(fecha=datetime.now(timezone.utc).isoformat(), python=platform.python_version(), sistema=platform.system(), arquitectura=platform.machine(),
                    docker=run(['docker', 'version', '--format', '{{.Server.Version}}'], capture_output=True, text=True).stdout.strip(),
                    paquetes={name: version(name) for name in ['fastapi', 'pydantic', 'pymongo', 'neo4j', 'redis', 'requests', 'pytest', 'uvicorn']})
    images = run(['docker', 'image', 'inspect', 'mongo:7.0', 'neo4j:5-community', 'redis:7.4-alpine', 'influxdb:3-core'], capture_output=True, text=True)
    versions['productos'] = {}
    for service, command in [('mongo', ['mongod', '--version']), ('neo4j', ['neo4j', '--version']),
                             ('redis', ['redis-server', '--version']), ('influxdb', ['influxdb3', '--version'])]:
        result = run(COMPOSE + ['exec', '-T', service] + command, capture_output=True, text=True, timeout=20)
        versions['productos'][service] = result.stdout.strip()
    versions['imagenes'] = [{key: image.get(key) for key in ['Id', 'RepoTags', 'RepoDigests', 'Architecture']} for image in json.loads(images.stdout)]
    (EVIDENCE / 'versiones.json').write_text(json.dumps(versions, indent=2) + '\n')
    (EVIDENCE / 'diagnostico_terminal.json').unlink()  # Misma salida ya guardada en completo.json.
    print('Cierre verificado. API temporal detenida; motores y volumenes del laboratorio conservados.')


if __name__ == '__main__':
    main()
