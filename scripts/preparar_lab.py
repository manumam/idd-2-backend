#!/usr/bin/env python3
"""Datos mínimos MongoDB/InfluxDB SOLO para un laboratorio descartable de validación."""
import argparse
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters import mongo_adapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laboratorio-descartable", required=True, action="store_true")
    parser.add_argument("--sources", default="mongodb", help="mongodb,influxdb")
    args = parser.parse_args()
    sources = set(args.sources.split(","))
    try:
        if "mongodb" in sources:
            seed_mongo()
        if "influxdb" in sources:
            seed_influx()
        if sources - {"mongodb", "influxdb"}:
            raise ValueError("Fuente de laboratorio desconocida")
        print("Datos sintéticos preparados: " + ",".join(sorted(sources)))
    finally:
        mongo_adapter.close()


def seed_mongo():
    db = mongo_adapter.db
    db.equipos.replace_one({"_id": "ARG"}, dict(_id="ARG", nombre="Argentina", confederacion="CONMEBOL", grupo="A", ranking_fifa=1, anfitrion=True), upsert=True)
    db.jugadores.replace_one({"_id": "ARG-10"}, dict(_id="ARG-10", nombre="Jugador", apellido="Demo", dorsal=10, posicion="Delantero", equipo={"_id": "ARG", "nombre": "Argentina"}, fecha_nacimiento=datetime(2000, 1, 1)), upsert=True)


def seed_influx():
    import requests
    from app.config.settings import settings
    headers = {"Authorization": "Bearer " + settings.influx_token} if settings.influx_token else {}
    response = requests.post(settings.influx_url + "/api/v3/write_lp", params={"db": settings.influx_database, "precision": "second"},
        headers=headers, data="estadisticas_partido,partido_id=P-001,equipo_id=ARG posesion_pct=60.0,tiros_acumulados=2i,pases_intervalo=10i 1908561600\n", timeout=10)
    response.raise_for_status()


if __name__ == "__main__":
    main()
