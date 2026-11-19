"""Copia el token de InfluxDB a observabilidad/secretos/ para que Prometheus scrapee su /metrics.

Busca el token en el mismo orden que la API (INFLUX_TOKEN, luego archivos .influxdb3-token)
y, por último, en el admin_token.json que genera el docker-compose de la raíz.
"""

import json
import os
import sys
from pathlib import Path

from generar_config_demo import ENV_BACKEND, leer_env

AQUI = Path(__file__).resolve().parent
BACKEND = AQUI.parent
DESTINO = AQUI / "secretos"
ARCHIVOS_TOKEN = (
    BACKEND / ".influxdb3-token",
    Path.home() / ".influxdb3-token",
    BACKEND.parent / "TP" / "fixture2030-influxdb" / ".influxdb3-token",
)
ADMIN_TOKEN_JSON = Path.home() / "docker" / "data" / "influxdb" / "admin_token.json"


def buscar_token() -> str:
    token = os.environ.get("INFLUX_TOKEN") or leer_env(ENV_BACKEND).get("INFLUX_TOKEN", "")
    if token:
        return token
    for ruta in ARCHIVOS_TOKEN:
        if ruta.is_file() and (token := ruta.read_text(encoding="utf-8").strip()):
            return token
    if ADMIN_TOKEN_JSON.is_file():
        return json.loads(ADMIN_TOKEN_JSON.read_text(encoding="utf-8")).get("token", "")
    return ""


def main() -> None:
    token = buscar_token()
    if not token:
        sys.exit("No se encontró el token de InfluxDB (INFLUX_TOKEN o .influxdb3-token).")
    DESTINO.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DESTINO, 0o700)
    # 0644: Prometheus corre como `nobody` dentro del contenedor; la carpeta 0700 protege en el host.
    archivo = DESTINO / "influxdb_token"
    archivo.write_text(token, encoding="utf-8")
    os.chmod(archivo, 0o644)
    print(f"Token copiado a {archivo} (sin mostrarlo).")


if __name__ == "__main__":
    main()
