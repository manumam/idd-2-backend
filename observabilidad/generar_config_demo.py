"""Genera la config de Prometheus para la demo (entorno=demo + remote_write a Grafana Cloud).

Lee GRAFANA_CLOUD_PROM_URL, GRAFANA_CLOUD_PROM_USER y GRAFANA_CLOUD_PROM_TOKEN de las
variables exportadas o del .env del backend. Escribe en observabilidad/generado/ (ignorado por git).
"""

import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CONFIG_PRUEBA = AQUI / "prometheus" / "prometheus.yml"
DESTINO = AQUI / "generado"
ENV_BACKEND = AQUI.parent / ".env"
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


def config_demo(config_prueba: str, url: str, usuario: str) -> str:
    if "entorno: prueba" not in config_prueba:
        sys.exit(f"{CONFIG_PRUEBA} no tiene ningún target con 'entorno: prueba'.")
    config = config_prueba.replace("entorno: prueba", "entorno: demo")
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
    ruta_env = Path(sys.argv[1]) if len(sys.argv) > 1 else ENV_BACKEND
    destino = Path(sys.argv[2]) if len(sys.argv) > 2 else DESTINO
    valores = cargar_credenciales(ruta_env)

    destino.mkdir(mode=0o700, exist_ok=True)
    os.chmod(destino, 0o700)
    config = config_demo(
        CONFIG_PRUEBA.read_text(encoding="utf-8"),
        valores["GRAFANA_CLOUD_PROM_URL"],
        valores["GRAFANA_CLOUD_PROM_USER"],
    )
    (destino / "prometheus.yml").write_text(config, encoding="utf-8")

    # 0644: Prometheus corre como `nobody` dentro del contenedor; la carpeta 0700 protege en el host.
    password = destino / "grafana_cloud_password"
    password.write_text(valores["GRAFANA_CLOUD_PROM_TOKEN"], encoding="utf-8")
    os.chmod(password, 0o644)

    print(f"Config demo generada en {destino}/ (sin mostrar credenciales).")


if __name__ == "__main__":
    main()
