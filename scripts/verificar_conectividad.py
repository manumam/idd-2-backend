#!/usr/bin/env python3
"""Script CLI para verificar la conectividad de los cinco motores NoSQL.

Cumple con RF17, RNF11 y entrega de scripts de la consigna (§9):
- Ejecuta un ping activo sobre cada adaptador.
- Captura fallas de dependencia sin exponer credenciales ni fallar catastróficamente.
- Muestra una tabla clara en terminal con el estado de cada servicio.
"""

import sys
import os
import time

# Asegurar que el directorio raíz del proyecto esté en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config.settings import settings
from app.adapters import (
    mongo_adapter,
    neo4j_adapter,
    redis_adapter,
    influx_adapter,
)
from app.core.exceptions import DatabaseUnavailableError


def test_adapter(name: str, adapter_obj, target_info: str) -> tuple[bool, str, float]:
    """Prueba un adaptador específico y mide latencia."""
    start_time = time.time()
    try:
        adapter_obj.ping()
        elapsed = (time.time() - start_time) * 1000
        return True, "ONLINE", elapsed
    except DatabaseUnavailableError as e:
        elapsed = (time.time() - start_time) * 1000
        # Mensaje seguro sin exponer credenciales
        reason = e.original_error.__class__.__name__ if e.original_error else "Timeout/No disponible"
        return False, f"NO DISPONIBLE ({reason})", elapsed
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        return False, f"ERROR INESPERADO ({e.__class__.__name__})", elapsed
    finally:
        adapter_obj.close()


def main():
    print("\n" + "=" * 76)
    print("       FIXTURE 2030 - DIAGNÓSTICO DE CONECTIVIDAD NoSQL (HITO 10)")
    print("=" * 76)
    print(f" Timeout configurado por consulta: {settings.db_timeout_seconds} segundos\n")

    targets = [(name, adapter, "configuración de entorno") for name, adapter in [
        ("MongoDB", mongo_adapter), ("Neo4j", neo4j_adapter),
        ("Redis", redis_adapter),
        ("InfluxDB", influx_adapter),
    ]]

    results = []
    for name, adapter_obj, target_info in targets:
        print(f"Probando {name:<10} en {target_info} ...", end=" ", flush=True)
        is_online, status_text, elapsed = test_adapter(name, adapter_obj, target_info)
        results.append((name, target_info, is_online, status_text, elapsed))
        icon = "🟢" if is_online else "🔴"
        print(f"{icon} {status_text} ({elapsed:.1f} ms)")

    print("\n" + "-" * 76)
    print(" RESUMEN GENERAL")
    print("-" * 76)
    online_count = sum(1 for item in results if item[2])
    print(f" Total motores disponibles: {online_count} / {len(results)}")
    print("-" * 76 + "\n")
    return 0 if online_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
