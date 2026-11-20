#!/usr/bin/env python3
"""Simulación en vivo acelerada: MongoDB e InfluxDB avanzan al mismo ritmo de juego."""
import argparse
from datetime import datetime, timezone
from itertools import islice
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.adapters import influx_adapter, mongo_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.alineaciones import Alineaciones
from app.services.cache_partidos import patron_mapa_calor
from app.services.comparacion_service import consolidar
from scripts import cargar_influx
from scripts.cargar_alineaciones import Lote
from scripts.cargar_fixture import read_csv
from scripts.simular_estadisticas import (
    PlanEstadisticas, confirmar_tick, crear_plan_estadisticas, line_protocol, preparar_ejecucion, verificar_avance)

DURACION_SEG = cargar_influx.DURACION_PARTIDO_SEG
INTERVALO_RESUMEN_SEG = cargar_influx.INTERVALO_MUESTREO_SEG
FACTOR_POR_DEFECTO = 10
# Un lote por segundo real: con factor 10 agrupa diez segundos de juego por escritura.
CADENCIA_REAL_SEG = 1.0
ALINEACIONES_DEMO = (cargar_influx.DATA / 'alineaciones-p001-demo.json',
                     cargar_influx.DATA / 'alineaciones-argentina-demo.json')


class RelojSimulado:
    """Convierte tiempo real transcurrido en segundos de juego: factor 10 juega 90 minutos en 9."""

    def __init__(self, factor=FACTOR_POR_DEFECTO, duracion=DURACION_SEG):
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('El factor debe ser finito y positivo')
        self.factor = factor
        self.duracion = duracion

    def segundo_en(self, transcurrido_real):
        if transcurrido_real < 0:
            raise ValueError('El tiempo real no puede retroceder')
        return min(self.duracion, math.floor(transcurrido_real * self.factor))

    def transcurrido_para(self, segundo):
        return segundo / self.factor

    def pendientes(self, ultimo_escrito, transcurrido_real):
        """Segundos de juego vencidos y todavía no escritos; -1 indica que no se escribió ninguno."""
        return range(ultimo_escrito + 1, self.segundo_en(transcurrido_real) + 1)


def ticks_vencidos(ticks, siguiente, segundo):
    """Índices de los ticks del guion cuyo minuto ya se alcanzó, empezando por `siguiente`."""
    vencidos = []
    for i in range(siguiente, len(ticks)):
        if ticks[i].reloj.minuto * 60 > segundo:
            break
        vencidos.append(i)
    return vencidos


def inicio_tracking_desde(ahora):
    # Mismo redondeo que el mapa de calor: sus minutos se cuentan desde el minuto exacto.
    return ahora.astimezone(timezone.utc).replace(second=0, microsecond=0)


def titulares_de(alineaciones, local, visitante):
    """Titulares de las plazas actuales, local primero: el mismo orden que la carga masiva."""
    titulares = []
    for lado, equipo in (('local', local), ('visitante', visitante)):
        alineacion = getattr(alineaciones, lado)
        if alineacion is None:
            continue
        if alineacion.equipo.codigo != equipo.codigo:
            raise ValueError(f'La alineación {lado} no corresponde a la selección del partido')
        titulares += [(cargar_influx._tag(j.codigo), equipo.codigo) for j in alineacion.titulares]
    return titulares


def titulares_de_archivos(archivos, plan):
    for archivo in archivos:
        for entrada in Lote.model_validate_json(Path(archivo).read_text()).partidos:
            if entrada.partido == plan.deportivo.partido:
                return titulares_de(entrada.alineaciones, plan.local, plan.visitante)
    return titulares_de(Alineaciones(), plan.local, plan.visitante)


def confederaciones_del_torneo(import_dir=cargar_influx.DATA / 'import'):
    return sorted({cargar_influx._tag(e['confederacion']) for e in read_csv(Path(import_dir) / 'equipos.csv')})


class GeneradorMuestras:
    """Line protocol de cada segundo de juego, sin escribir.

    Tracking y audiencia reutilizan los generadores de la carga masiva, anclados en
    inicio_tracking: mismos valores por segundo, otra hora. Las estadísticas de equipo
    son las del caso 8, ancladas en el inicio del plan, que es lo que su comparación valida.
    Las secuencias son deterministas pero dependen de los segundos anteriores: se piden en orden.
    """

    def __init__(self, plan, titulares, confederaciones, inicio_tracking):
        self.plan = plan
        self.titulares = titulares
        self.confederaciones = confederaciones
        partido = dict(codigo=cargar_influx._tag(plan.deportivo.partido),
                       inicio=int(inicio_tracking.timestamp()), titulares=titulares)
        self._jugadores = cargar_influx.lineas_tracking_jugador(partido)
        self._pelota = cargar_influx.lineas_tracking_pelota(partido)
        self._audiencia = cargar_influx.lineas_actividad_usuarios(partido, confederaciones)
        self.siguiente = 0

    def lineas(self, desde, hasta):
        if desde != self.siguiente or hasta < desde or hasta > DURACION_SEG:
            raise ValueError('Los segundos de juego se generan en orden y sin huecos')
        tablas = {'tracking_jugador': [], 'tracking_pelota': [], 'estadisticas_partido': [], 'actividad_usuarios': []}
        for segundo in range(desde, hasta + 1):
            # La carga masiva muestrea [0, 5400); el resumen del caso 8 incluye el cierre en 5400.
            if segundo < DURACION_SEG:
                tablas['tracking_jugador'] += islice(self._jugadores, len(self.titulares))
                tablas['tracking_pelota'] += islice(self._pelota, 1)
                if segundo % INTERVALO_RESUMEN_SEG == 0:
                    tablas['actividad_usuarios'] += islice(self._audiencia, len(self.confederaciones))
        primero = -(-desde // INTERVALO_RESUMEN_SEG) * INTERVALO_RESUMEN_SEG
        if primero <= hasta:
            tablas['estadisticas_partido'] = line_protocol(self.plan, self.plan.muestras(primero, hasta)).splitlines()
        self.siguiente = hasta + 1
        return tablas


def bases_configuradas():
    # Las mismas bases que leen el mapa de calor (en vivo) y la comparación de equipos (resumen).
    from app.config.settings import settings
    return {'tracking_jugador': settings.influx_database_en_vivo, 'tracking_pelota': settings.influx_database_en_vivo,
            'estadisticas_partido': settings.influx_database, 'actividad_usuarios': settings.influx_database}


class EscritorInflux:
    """Un lote por tabla y tick, con los reintentos de la carga masiva y contadores por tabla."""

    def __init__(self, session, url, token, bases):
        self.session, self.url, self.token, self.bases = session, url, token, bases
        self.contadores = {tabla: dict(base=base, escritas=0, rechazadas=0) for tabla, base in bases.items()}

    def escribir(self, lineas_por_tabla):
        rechazadas = 0
        for tabla, lineas in lineas_por_tabla.items():
            if not lineas:
                continue
            fallidas = cargar_influx.escribir(self.session, self.url, self.token, self.bases[tabla], lineas)
            self.contadores[tabla]['escritas'] += len(lineas) - fallidas
            self.contadores[tabla]['rechazadas'] += fallidas
            rechazadas += fallidas
        return rechazadas


def invalidar_mapa_calor(codigo):
    try:
        redis_adapter.delete_cache_matching(patron_mapa_calor(codigo))
    except DatabaseUnavailableError:
        # Redis es opcional: el TTL de 5 s del mapa en vivo limita la antigüedad.
        pass


def simular(plan, factor, titulares, confederaciones, escritor, reloj=time.monotonic, dormir=time.sleep,
            ahora=None, informar=print):
    """Avanza el partido en tiempo real acelerado hasta finalizarlo. No es reanudable."""
    codigo = plan.deportivo.partido
    doc = mongo_adapter.find_estadisticas(codigo)
    if not doc:
        raise ValueError('Partido inexistente')
    if doc.get('estadisticas_control') or doc.get('inicio_tracking'):
        raise ValueError('El partido ya tuvo una simulación: restaurarlo o elegir otro próximo')
    inicio_tracking = inicio_tracking_desde(ahora or datetime.now(timezone.utc))
    # inicio_tracking se guarda junto con el control inicial del caso 8, en una sola escritura.
    control = preparar_ejecucion(plan, {'inicio_tracking': inicio_tracking})
    generador = GeneradorMuestras(plan, titulares, confederaciones, inicio_tracking)
    reloj_juego = RelojSimulado(factor)
    escrito, siguiente_tick = -1, 0
    origen = reloj()
    while escrito < DURACION_SEG:
        comienzo = reloj() - origen
        pendientes = reloj_juego.pendientes(escrito, comienzo)
        if pendientes:
            # Influx antes que MongoDB: un tick solo se confirma con sus muestras ya escritas.
            if escritor.escribir(generador.lineas(pendientes.start, pendientes[-1])):
                raise ValueError('InfluxDB rechazó muestras después de los reintentos')
            escrito = pendientes[-1]
            for i in ticks_vencidos(plan.deportivo.ticks, siguiente_tick, escrito):
                verificar_avance(plan, control)
                control = confirmar_tick(plan, i, control)
                invalidar_mapa_calor(codigo)
                siguiente_tick = i + 1
                tick = plan.deportivo.ticks[i]
                informar(json.dumps(dict(partido=codigo, tick=i + 1, minuto=tick.reloj.minuto,
                                         segundo_de_juego=escrito, finalizado=tick.finalizado)))
        if escrito < DURACION_SEG:
            proximo = max(reloj_juego.transcurrido_para(escrito + 1), comienzo + CADENCIA_REAL_SEG)
            espera = proximo - (reloj() - origen)
            if espera > 0:
                dormir(espera)
    resumen = consolidar(codigo)
    return dict(partido=codigo, inicio_tracking=inicio_tracking.strftime('%Y-%m-%dT%H:%M:%SZ'),
                factor=factor, tablas=escritor.contadores, consolidacion=resumen.consolidacion)


def contar_puntos(plan, titulares, confederaciones):
    generador = GeneradorMuestras(plan, titulares, confederaciones, datetime.now(timezone.utc))
    return {tabla: len(lineas) for tabla, lineas in generador.lineas(0, DURACION_SEG).items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archivo', type=Path, help='Plan del caso 8 (simular_estadisticas.py); ver docs/simulador_en_vivo.md')
    parser.add_argument('--crear-plan', metavar='CODIGO', help='Genera el plan leyendo catálogos, sin escribir en las bases')
    parser.add_argument('--solo-validar', action='store_true', help='Valida el plan y cuenta puntos sin conectar a bases')
    parser.add_argument('--factor', type=float, default=FACTOR_POR_DEFECTO, help='Segundos de juego por segundo real')
    parser.add_argument('--alineaciones', type=Path, action='append',
                        help='Solo con --solo-validar: lotes versionados de alineaciones; por defecto los de demo')
    args = parser.parse_args()
    try:
        reloj_juego = RelojSimulado(args.factor)
    except ValueError as exc:
        parser.error(str(exc))
    if args.alineaciones and not args.solo_validar:
        parser.error('--alineaciones se usa con --solo-validar; la ejecución lee las alineaciones de MongoDB')
    if args.crear_plan:
        if args.archivo.exists():
            parser.error('El archivo ya existe; elegir otro nombre')
        plan = crear_plan_estadisticas(args.crear_plan)
        args.archivo.write_text(plan.model_dump_json(indent=2) + '\n')
        print(json.dumps(dict(archivo=str(args.archivo), partido=plan.deportivo.partido, bases_modificadas=False)))
        return
    plan = PlanEstadisticas.model_validate_json(args.archivo.read_text())
    confederaciones = confederaciones_del_torneo()
    if args.solo_validar:
        titulares = titulares_de_archivos(args.alineaciones or ALINEACIONES_DEMO, plan)
        print(json.dumps(dict(partido=plan.deportivo.partido, factor=args.factor,
            duracion_real_s=reloj_juego.transcurrido_para(DURACION_SEG),
            ticks=[dict(minuto=t.reloj.minuto, segundo_real=reloj_juego.transcurrido_para(t.reloj.minuto * 60))
                   for t in plan.deportivo.ticks],
            jugadores_con_tracking=len(titulares), puntos=contar_puntos(plan, titulares, confederaciones),
            bases_modificadas=False, referencias_verificadas=False), indent=2))
        return
    import requests
    from app.config.settings import settings
    documento = mongo_adapter.find_alineaciones(plan.deportivo.partido) or {}
    titulares = titulares_de(Alineaciones.model_validate(documento.get('alineaciones') or {}), plan.local, plan.visitante)
    with requests.Session() as session:
        escritor = EscritorInflux(session, settings.influx_url, influx_adapter._resolve_token(), bases_configuradas())
        print(json.dumps(simular(plan, args.factor, titulares, confederaciones, escritor), indent=2))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Simulación detenida. No es reanudable: restaurar el partido o elegir otro próximo.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'Simulación interrumpida: {type(exc).__name__}. No es reanudable: revisar plan, referencias '
              'y conexiones; restaurar el partido o elegir otro próximo.', file=sys.stderr)
        sys.exit(1)
    finally:
        mongo_adapter.close()
        influx_adapter.close()
        redis_adapter.close()
