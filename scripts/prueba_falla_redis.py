#!/usr/bin/env python3
"""Detiene y restaura exclusivamente Redis del Compose aislado Hito 11."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluar_conectividad import api_probe

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.hito11.yaml')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18000')
    parser.add_argument('--salida', type=Path, default=ROOT / 'docs/hito_11/evidencia/falla_redis.json')
    args = parser.parse_args()
    rows = []
    def check(stage, path, expected):
        start = time.perf_counter()
        row = api_probe(args.base_url.rstrip('/'), path)
        row.update(etapa=stage, fecha=datetime.now(timezone.utc).isoformat(), duracion_ms=round((time.perf_counter()-start)*1000, 2), esperado=expected)
        row['correcto'] = row['status_http'] == expected and row['request_id'] == row['correlacion_esperada']
        rows.append(row)
        return row['correcto']
    def check_group(stage, session, ready):
        return all([check(stage, '/live', 200), check(stage, '/health', 200),
                    check(stage, '/ready', ready), check(stage, '/sesiones/SES-DEMO', session)])
    try:
        if not check_group('inicial', 200, 200):
            raise RuntimeError('Preparar los datos y las cuatro dependencias antes de detener Redis')
        try:
            subprocess.run(COMMAND + ['stop', 'redis'], check=True, timeout=30)
            if not check_group('detenido', 503, 503):
                raise RuntimeError('Respuesta inesperada con Redis detenido')
        finally:
            subprocess.run(COMMAND + ['start', 'redis'], check=True, timeout=30)
        for attempt in range(10):
            if check('recuperacion', '/ready', 200):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Redis no recuperado dentro del plazo')
        if not check_group('recuperado', 200, 200):
            raise RuntimeError('La sesion no se recupero')
    finally:
        report = dict(resultados=rows, persistencia='Volumen redis_lab conservado; no se borraron datos ni volumenes.')
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(report, indent=2) + '\n')
    print('Redis y readiness recuperados. Liveness siempre 200. Evidencia guardada.')


if __name__ == '__main__':
    main()
