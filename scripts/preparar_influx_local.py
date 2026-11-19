#!/usr/bin/env python3
"""Configura la instancia propia del caso 8; no carga muestras ni datos deportivos."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from dotenv import dotenv_values, set_key


def main():
    os.chdir(ROOT)
    container = 'fixture2030-estadisticas-influxdb'
    result = subprocess.run(['docker', 'inspect', container, '--format',
        '{{index .Config.Labels "com.docker.compose.project"}}'], capture_output=True, text=True, check=True)
    if result.stdout.strip() != 'fixture2030-estadisticas':
        raise ValueError('El contenedor no pertenece al Compose propio')
    port = os.environ.get('INFLUX_ESTADISTICAS_PORT', '8181')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError('Puerto inválido')
    url = f'http://127.0.0.1:{int(port)}'
    result = subprocess.run(['docker', 'exec', container, 'cat', '/var/lib/influxdb3/admin_token.json'],
        capture_output=True, text=True, check=True)
    token = json.loads(result.stdout)['token']
    env = ROOT / '.env'
    values = dotenv_values(env) if env.exists() else {}
    database = os.environ.get('INFLUX_DATABASE') or values.get('INFLUX_DATABASE') or 'fixture2030_resumen'
    if not re.fullmatch(r'[A-Za-z0-9_-]+', database):
        raise ValueError('Nombre de base inválido')
    response = requests.post(url + '/api/v3/configure/database',
        headers={'Authorization': 'Bearer ' + token}, json={'db': database}, timeout=10)
    if response.status_code != 200:
        # Un reintento acepta solo la existencia verificada de la base propia.
        check = requests.get(url + '/api/v3/configure/database', params={'format': 'json'},
            headers={'Authorization': 'Bearer ' + token}, timeout=10)
        check.raise_for_status()
        names = check.json()
        if not any((d == database if isinstance(d, str) else d.get('iox::database') == database or d.get('db_name') == database or d.get('name') == database) for d in names):
            raise ValueError('No se pudo crear/verificar la base propia')
    backup = ROOT / '.env.antes-estadisticas'
    if env.exists() and not backup.exists():
        shutil.copyfile(env, backup)
        backup.chmod(0o600)
    for key, value in {'INFLUX_URL': url, 'INFLUX_DATABASE': database, 'INFLUX_TOKEN': token}.items():
        set_key(env, key, value)
    env.chmod(0o600)
    print('Influx propio configurado. Se conservan las otras variables y una copia local privada de .env.')
    print('Sin muestras ni cambios deportivos.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Configuración interrumpida: {type(exc).__name__}. Revisar contenedor, puerto y conexión.', file=sys.stderr)
        sys.exit(1)
