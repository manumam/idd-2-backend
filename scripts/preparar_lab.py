#!/usr/bin/env python3
"""Datos mínimos Mongo/Redis SOLO para un laboratorio descartable de validación."""
import argparse
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adapters import mongo_adapter, redis_adapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--laboratorio-descartable", required=True, action="store_true")
    parser.add_argument("--sources", default="mongodb,redis", help="mongodb,redis,neo4j,cassandra,influxdb,iris")
    args = parser.parse_args()
    sources = set(args.sources.split(","))
    try:
        if "mongodb" in sources:
            seed_mongo()
        if "redis" in sources:
            seed_redis()
        for source in sources - {"mongodb", "redis"}:
            seed_extra(source)
        print("Datos sintéticos preparados: " + ",".join(sorted(sources)))
    finally:
        for adapter in (mongo_adapter, redis_adapter):
            adapter.close()


def seed_mongo():
    db = mongo_adapter.db
    db.equipos.replace_one({"_id": "ARG"}, dict(_id="ARG", nombre="Argentina", confederacion="CONMEBOL", grupo="A", ranking_fifa=1, anfitrion=True), upsert=True)
    db.jugadores.replace_one({"_id": "ARG-10"}, dict(_id="ARG-10", nombre="Jugador", apellido="Demo", dorsal=10, posicion="Delantero", equipo={"_id": "ARG", "nombre": "Argentina"}, fecha_nacimiento=datetime(2000, 1, 1)), upsert=True)


def seed_redis():
    redis_adapter.client.hset("sesion:SES-DEMO", mapping=dict(usuario_id="U001", nombre_usuario="Demo", rol="hincha", idioma="es", acciones="1"))
    redis_adapter.client.expire("sesion:SES-DEMO", 3600)


def seed_extra(source):
    from app.adapters import cassandra_adapter, neo4j_adapter, iris_adapter
    from app.config.settings import settings
    from datetime import timezone
    from uuid import UUID
    import requests
    if source == "neo4j":
        neo4j_adapter._run("""
        MERGE (p:Partido {id:'P-001'}) SET p.fase='Grupos', p.grupo='A', p.fecha=date('2030-06-24')
        MERGE (s:Sede {id:'S-04'}) SET s.nombre='Estadio Demo', s.ciudad='Buenos Aires'
        MERGE (p)-[:SE_DISPUTA_EN]->(s)
        MERGE (e:Equipo {id:'ARG'}) SET e.nombre='Argentina', e.confederacion='CONMEBOL'
        MERGE (e)-[:PARTICIPA_EN {condicion:'Local'}]->(p)
        MERGE (v:Equipo {id:'ESP'}) SET v.nombre='España'
        MERGE (v)-[:PARTICIPA_EN {condicion:'Visitante'}]->(p)
        MERGE (j:Jugador {id:'ARG-10'}) SET j.nombre='Jugador', j.apellido='Demo'
        MERGE (j)-[:PERTENECE_A]->(e)
        MERGE (ev:Evento {id:'E-0001'}) SET ev.tipo='Gol', ev.minuto=15
        MERGE (ev)-[:OCURRE_EN]->(p) MERGE (j)-[:PROTAGONIZA {rol:'autor'}]->(ev)
        RETURN p.id AS id
        """)
        neo4j_adapter.close()
    elif source == "cassandra":
        for id in ("ba894580-ec17-11f5-8123-0242ac120002", "11424f80-ec17-11f5-8123-0242ac120002"):
            cassandra_adapter.session.execute(
                "INSERT INTO comentarios_feed (partido_id,bloque_temporal,comentario_id,idioma,usuario_id,nombre_usuario,texto,estado_moderacion) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                ["ARG-ESP-20300624", datetime(2030,6,24,20,5,tzinfo=timezone.utc), UUID(id), "es", "U001", "Demo", "Vamos", "APROBADO"])
        cassandra_adapter.close()
    elif source == "influxdb":
        headers = {"Authorization": "Bearer " + settings.influx_token} if settings.influx_token else {}
        response = requests.post(settings.influx_url + "/api/v3/write_lp", params={"db": settings.influx_database, "precision": "second"},
            headers=headers, data="estadisticas_partido,partido_id=P-001,equipo_id=ARG posesion_pct=60.0,tiros_acumulados=2i,pases_intervalo=10i 1908561600\n", timeout=10)
        response.raise_for_status()
    elif source == "iris":
        with iris_adapter._cursor() as cursor:
            cursor.execute("INSERT INTO Fixture.Partido (Codigo, Estado) VALUES (?, ?)", ["P-001", "Finalizado"])
            cursor.execute("SELECT TOP 1 ID FROM Fixture.Partido WHERE Codigo = ? ORDER BY ID DESC", ["P-001"])
            id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO Fixture.Evento (Tipo, Minuto, Partido) VALUES (?, ?, ?)", ["Gol", 15, id])
            print(f"IRIS_TEST_ID={id}")
    else:
        raise ValueError("Fuente de laboratorio desconocida")


if __name__ == "__main__":
    main()
