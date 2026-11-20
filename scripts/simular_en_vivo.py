#!/usr/bin/env python3
"""Simulación en vivo acelerada: MongoDB e InfluxDB avanzan al mismo ritmo de juego."""
from datetime import timezone
from itertools import islice
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.schemas.alineaciones import Alineaciones
from scripts import cargar_influx
from scripts.cargar_alineaciones import Lote
from scripts.cargar_fixture import read_csv
from scripts.simular_estadisticas import line_protocol

DURACION_SEG = cargar_influx.DURACION_PARTIDO_SEG
INTERVALO_RESUMEN_SEG = cargar_influx.INTERVALO_MUESTREO_SEG
FACTOR_POR_DEFECTO = 10


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
