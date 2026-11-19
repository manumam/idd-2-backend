"""Genera la config de Prometheus que envía las métricas a Grafana Cloud con la etiqueta `entorno` elegida.

Lee GRAFANA_CLOUD_PROM_URL, GRAFANA_CLOUD_PROM_USER y GRAFANA_CLOUD_PROM_TOKEN de las
variables exportadas o del .env del backend. Escribe en observabilidad/generado/ (ignorado por git).
"""

import argparse
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CONFIG_BASE = AQUI / "prometheus" / "prometheus.yml"
DESTINO = AQUI / "generado"
ENV_BACKEND = AQUI.parent / ".env"
ENTORNO_BASE = "entorno: prueba"
ENTORNOS = ("prueba", "demo")
RUTA_PASSWORD_EN_CONTENEDOR = "/etc/prometheus/grafana_cloud_password"
VARIABLES = ("GRAFANA_CLOUD_PROM_URL", "GRAFANA_CLOUD_PROM_USER", "GRAFANA_CLOUD_PROM_TOKEN")


def leer_env(ruta: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not ruta.is_file():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip("'\"")
    return valores


def cargar_credenciales(ruta_env: Path) -> dict[str, str]:
    archivo = leer_env(ruta_env)
    # Las variables exportadas tienen prioridad sobre el .env.
    valores = {nombre: os.environ.get(nombre) or archivo.get(nombre, "") for nombre in VARIABLES}
    faltantes = [nombre for nombre, valor in valores.items() if not valor]
    if faltantes:
        sys.exit(f"Faltan variables: {', '.join(faltantes)} (en .env o exportadas).")
    if not valores["GRAFANA_CLOUD_PROM_URL"].startswith("https://"):
        sys.exit("GRAFANA_CLOUD_PROM_URL debe empezar con https://")
    return valores


def config_nube(config_base: str, entorno: str, url: str, usuario: str) -> str:
    if ENTORNO_BASE not in config_base:
        sys.exit(f"{CONFIG_BASE} no tiene ningún target con '{ENTORNO_BASE}'.")
    config = config_base.replace(ENTORNO_BASE, f"entorno: {entorno}")
    # Valores en JSON: un string JSON es un string YAML válido y queda bien escapado.
    return (
        config.rstrip("\n")
        + "\n\n# encontrado en documentación de Grafana Cloud\n"
        + "remote_write:\n"
        + f"  - url: {json.dumps(url)}\n"
        + "    basic_auth:\n"
        + f"      username: {json.dumps(usuario)}\n"
        + f"      password_file: {RUTA_PASSWORD_EN_CONTENEDOR}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entorno", required=True, choices=ENTORNOS)
    parser.add_argument("--env", type=Path, default=ENV_BACKEND)
    parser.add_argument("--destino", type=Path, default=DESTINO)
    args = parser.parse_args()
    valores = cargar_credenciales(args.env)

    args.destino.mkdir(mode=0o700, exist_ok=True)
    os.chmod(args.destino, 0o700)
    config = config_nube(
        CONFIG_BASE.read_text(encoding="utf-8"),
        args.entorno,
        valores["GRAFANA_CLOUD_PROM_URL"],
        valores["GRAFANA_CLOUD_PROM_USER"],
    )
    (args.destino / "prometheus.yml").write_text(config, encoding="utf-8")

    # 0644: Prometheus corre como `nobody` dentro del contenedor; la carpeta 0700 protege en el host.
    password = args.destino / "grafana_cloud_password"
    password.write_text(valores["GRAFANA_CLOUD_PROM_TOKEN"], encoding="utf-8")
    os.chmod(password, 0o644)

    print(f"Config con entorno={args.entorno} generada en {args.destino}/ (sin mostrar credenciales).")


if __name__ == "__main__":
    main()
