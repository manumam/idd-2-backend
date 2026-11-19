#!/usr/bin/env python3
"""Materializa ocupacion_jugador_minuto en el resumen desde el tracking crudo. No se ejecuta al iniciar la API."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.grilla_cancha import Celda, id_celda, parametros_grilla  # noqa: E402

MEDICION = 'ocupacion_jugador_minuto'

# encontrado en documentación de InfluxDB (SQL: date_bin, floor, least)
# La celda se calcula en InfluxDB; LEAST lleva el borde lejano (x = 105, y = 68) a la última celda.
SQL_OCUPACION = (
    "SELECT jugador_id, equipo_id, date_bin(INTERVAL '1 minute', time) AS minuto, "
    "LEAST(FLOOR(x_m / $lado_m), $ultima_columna) AS columna, "
    "LEAST(FLOOR(y_m / $lado_m), $ultima_fila) AS fila, "
    "COUNT(*) AS muestras "
    "FROM tracking_jugador "
    "WHERE partido_id = $partido AND x_m BETWEEN 0 AND $largo_m AND y_m BETWEEN 0 AND $ancho_m "
    "GROUP BY jugador_id, equipo_id, minuto, columna, fila"
)

SQL_OCUPACION_PARTIDO = (
    "SELECT jugador_id, "
    "LEAST(FLOOR(x_m / $lado_m), $ultima_columna) AS columna, "
    "LEAST(FLOOR(y_m / $lado_m), $ultima_fila) AS fila, "
    "COUNT(*) AS muestras "
    "FROM tracking_jugador "
    "WHERE partido_id = $partido AND x_m BETWEEN 0 AND $largo_m AND y_m BETWEEN 0 AND $ancho_m "
    "GROUP BY jugador_id, columna, fila"
)

SQL_PARTIDOS_CON_TRACKING = "SELECT DISTINCT partido_id FROM tracking_jugador ORDER BY partido_id"

SQL_MATERIALIZADO = (
    f"SELECT jugador_id, celda, time FROM {MEDICION} WHERE partido_id = $partido"
)


def _cargar_influx():
    spec = importlib.util.spec_from_file_location('cargar_influx', ROOT / 'scripts/cargar_influx.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


cargar_influx = _cargar_influx()


def parametros_consulta(partido):
    return dict(parametros_grilla(), partido=partido)


def _segundos(instante):
    # query_sql devuelve el tiempo en UTC sin zona, p. ej. '2030-06-09T13:00:00'.
    return int(datetime.fromisoformat(instante).replace(tzinfo=timezone.utc).timestamp())


def _celda(fila):
    return id_celda(Celda(int(fila['columna']), int(fila['fila'])))


def linea_ocupacion(partido, fila):
    tag = cargar_influx._tag
    return (f'{MEDICION},partido_id={tag(partido)},equipo_id={tag(fila["equipo_id"])},'
            f'jugador_id={tag(fila["jugador_id"])},celda={_celda(fila)} '
            f'muestras={int(fila["muestras"])}i {_segundos(fila["minuto"])}')


def leer_ocupacion(influx, base, partido):
    return influx.query_sql(SQL_OCUPACION, parametros_consulta(partido), base)


def validar(influx, base_en_vivo, base_resumen, partido):
    """Solo lectura: cuenta puntos y series y comprueba que las ventanas suman el total del partido."""
    filas = leer_ocupacion(influx, base_en_vivo, partido)
    por_minuto = Counter()
    for f in filas:
        por_minuto[(f['jugador_id'], _celda(f))] += int(f['muestras'])
    total = {(f['jugador_id'], _celda(f)): int(f['muestras'])
             for f in influx.query_sql(SQL_OCUPACION_PARTIDO, parametros_consulta(partido), base_en_vivo)}
    nuevas = {(f['jugador_id'], _celda(f), _segundos(f['minuto'])) for f in filas}
    existentes = {(f['jugador_id'], f['celda'], _segundos(f['time']))
                  for f in _leer_materializado(influx, base_resumen, partido)}
    return dict(
        partido=partido,
        puntos=len(filas),
        series=len({linea_ocupacion(partido, f).split(' ', 1)[0] for f in filas}),
        muestras=sum(por_minuto.values()),
        ventanas_suman_total=dict(por_minuto) == total,
        puntos_obsoletos=len(existentes - nuevas),
    )


def _leer_materializado(influx, base_resumen, partido):
    from app.core.exceptions import DatabaseUnavailableError
    try:
        return influx.query_sql(SQL_MATERIALIZADO, {'partido': partido}, base_resumen)
    except DatabaseUnavailableError:
        # Antes de la primera escritura la tabla no existe y InfluxDB rechaza la consulta.
        return []


def invalidar_mapas(conectar, partido):
    from redis.exceptions import RedisError
    from app.adapters.redis_adapter import borrar_por_patron
    from app.services.cache_partidos import patron_mapa_calor
    try:
        with conectar() as cache:
            borrar_por_patron(cache, patron_mapa_calor(partido))
        return True
    except RedisError:
        print(f'Advertencia: no se pudo invalidar la caché del mapa de calor de {partido}; esperar su TTL.',
              file=sys.stderr)
        return False


def materializar(influx, escribir, conectar, base_en_vivo, base_resumen, partido):
    lineas = [linea_ocupacion(partido, f) for f in leer_ocupacion(influx, base_en_vivo, partido)]
    rechazadas = escribir(base_resumen, lineas)
    invalidar_mapas(conectar, partido)
    return dict(partido=partido, enviadas=len(lineas), rechazadas=rechazadas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument('--partido', action='append', help='Uno o más partidos, p. ej. P-002')
    destino.add_argument('--todos', action='store_true', help='Todos los partidos con tracking_jugador')
    parser.add_argument('--solo-validar', action='store_true',
                        help='Solo lee: cuenta puntos y series y verifica la suma de ventanas, sin escribir')
    args = parser.parse_args()

    import requests
    from app.adapters.influx_adapter import influx_adapter
    from app.config.settings import settings
    from app.services.cache_partidos import conectar_cache
    base_en_vivo, base_resumen = settings.influx_database_en_vivo, settings.influx_database

    if args.todos:
        partidos = [f['partido_id'] for f in influx_adapter.query_sql(SQL_PARTIDOS_CON_TRACKING, None, base_en_vivo)]
    else:
        partidos = [cargar_influx._tag(p) for p in args.partido]

    if args.solo_validar:
        resultado = [validar(influx_adapter, base_en_vivo, base_resumen, p) for p in partidos]
        print(json.dumps(resultado, indent=2))
        if not all(r['ventanas_suman_total'] for r in resultado):
            sys.exit(1)
        return

    token = influx_adapter._resolve_token()
    with requests.Session() as session:
        def escribir(base, lineas):
            return cargar_influx.escribir(session, settings.influx_url, token, base, lineas)

        resultado = [materializar(influx_adapter, escribir, lambda: conectar_cache(settings),
                                  base_en_vivo, base_resumen, p) for p in partidos]
    print(json.dumps(resultado, indent=2))
    if any(r['rechazadas'] for r in resultado):
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Materialización interrumpida: {type(exc).__name__}. Revisar InfluxDB y los partidos indicados.',
              file=sys.stderr)
        sys.exit(1)
