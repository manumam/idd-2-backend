#!/usr/bin/env python3
"""Genera y carga en InfluxDB 3 las series sintéticas del torneo. No se ejecuta al iniciar la API."""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import random
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / 'data/fixture'

SEMILLA = 2030
DURACION_PARTIDO_SEG = 5400
INTERVALO_MUESTREO_SEG = 5
LOTE_LINEAS = 10000
INTENTOS_POR_LOTE = 3

BASE_EN_VIVO = 'fixture2030_en_vivo'
BASE_RESUMEN = 'fixture2030_resumen'
# Clase 9: el crudo de 1 s vence a los 7 días; el resumen no tiene vencimiento.
RETENCION = {BASE_EN_VIVO: '7d', BASE_RESUMEN: None}
AUDIENCIA_BASE = {'UEFA': 250000, 'CONMEBOL': 250000}
VALOR_TAG = re.compile(r'[A-Za-z0-9_-]+')


def _modulo(nombre):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / f'scripts/{nombre}.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _tag(valor):
    if not VALOR_TAG.fullmatch(valor):
        raise ValueError(f'Valor de tag inválido para Line Protocol: {valor!r}')
    return valor


def leer_titulares(archivos, partidos):
    """Toma solo titulares de alineaciones versionadas; no inventa convocatorias desde el plantel."""
    Lote = _modulo('cargar_alineaciones').Lote
    titulares = defaultdict(list)
    vistos = set()
    for archivo in archivos:
        for entrada in Lote.model_validate_json(Path(archivo).read_text()).partidos:
            partido = partidos.get(entrada.partido)
            if partido is None:
                raise ValueError(f'Alineación de un partido inexistente: {entrada.partido}')
            for lado in ('local', 'visitante'):
                alineacion = getattr(entrada.alineaciones, lado)
                if alineacion is None:
                    continue
                if (entrada.partido, lado) in vistos:
                    raise ValueError(f'Alineación repetida: {entrada.partido}/{lado}')
                vistos.add((entrada.partido, lado))
                equipo = (partido[lado] or {}).get('codigo')
                if alineacion.equipo.codigo != equipo:
                    raise ValueError(f'La selección no coincide con la plaza del partido: {entrada.partido}/{lado}')
                titulares[entrada.partido] += [(_tag(j.codigo), equipo) for j in alineacion.titulares]
    return titulares


def preparar(import_dir=DATA / 'import', calendario=DATA / 'fixture-calendario.json', alineaciones=(DATA / 'alineaciones-argentina-demo.json',)):
    fixture = _modulo('cargar_fixture')
    docs = {d['_id']: d for d in fixture.preparar(Path(import_dir), Path(calendario))}
    confederaciones = sorted({_tag(e['confederacion']) for e in fixture.read_csv(Path(import_dir) / 'equipos.csv')})
    titulares = leer_titulares(alineaciones, docs)
    partidos = []
    for codigo, d in sorted(docs.items()):
        partidos.append(dict(
            codigo=_tag(codigo),
            inicio=int(d['fecha_hora'].timestamp()),
            sede=_tag(d['sede']['codigo']),
            equipos=[_tag(d[lado]['codigo']) for lado in ('local', 'visitante') if d[lado]],
            titulares=titulares.get(codigo, []),
        ))
    return partidos, confederaciones


def _azar(tabla, partido):
    # Una secuencia por tabla y partido: generar un solo partido da los mismos puntos que el torneo completo.
    return random.Random(f'{SEMILLA}:{tabla}:{partido["codigo"]}')


def lineas_tracking_pelota(partido, _confederaciones=None):
    azar = _azar('tracking_pelota', partido)
    x, y = 52.5, 34.0
    for s in range(DURACION_PARTIDO_SEG):
        x = max(1.0, min(104.0, x + azar.uniform(-1.5, 1.5)))
        y = max(1.0, min(67.0, y + azar.uniform(-1.2, 1.2)))
        z = 0.0 if azar.random() > 0.25 else azar.uniform(0.1, 4.0)
        velocidad = azar.uniform(5.0, 95.0)
        yield (f'tracking_pelota,partido_id={partido["codigo"]} '
               f'x_m={x:.2f},y_m={y:.2f},z_m={z:.2f},velocidad_kmh={velocidad:.2f} {partido["inicio"] + s}')


def lineas_tracking_jugador(partido, _confederaciones=None):
    azar = _azar('tracking_jugador', partido)
    estado = {j: dict(x=azar.uniform(10.0, 95.0), y=azar.uniform(10.0, 58.0), distancia=0.0) for j, _ in partido['titulares']}
    for s in range(DURACION_PARTIDO_SEG):
        for jugador, equipo in partido['titulares']:
            e = estado[jugador]
            velocidad = round(azar.uniform(0.0, 31.5), 2)
            e['distancia'] += velocidad / 3.6
            e['x'] = max(0.5, min(104.5, e['x'] + azar.uniform(-0.8, 0.8)))
            e['y'] = max(0.5, min(67.5, e['y'] + azar.uniform(-0.6, 0.6)))
            yield (f'tracking_jugador,partido_id={partido["codigo"]},equipo_id={equipo},jugador_id={jugador} '
                   f'x_m={e["x"]:.2f},y_m={e["y"]:.2f},velocidad_kmh={velocidad:.2f},distancia_acum_m={e["distancia"]:.2f} '
                   f'{partido["inicio"] + s}')


def lineas_estadisticas_partido(partido, _confederaciones=None):
    azar = _azar('estadisticas_partido', partido)
    tiros = {equipo: 0 for equipo in partido['equipos']}
    for s in range(0, DURACION_PARTIDO_SEG, INTERVALO_MUESTREO_SEG):
        posesion_local = round(azar.uniform(40.0, 60.0), 1)
        posesiones = [posesion_local, round(100.0 - posesion_local, 1)]
        for equipo in tiros:
            if azar.random() < 0.04:
                tiros[equipo] += 1
        for equipo, posesion in zip(partido['equipos'], posesiones):
            pases = azar.randint(2, 9)
            yield (f'estadisticas_partido,partido_id={partido["codigo"]},equipo_id={equipo},sede_id={partido["sede"]} '
                   f'posesion_pct={posesion:.1f},tiros_acumulados={tiros[equipo]}i,pases_intervalo={pases}i '
                   f'{partido["inicio"] + s}')


def lineas_actividad_usuarios(partido, confederaciones):
    azar = _azar('actividad_usuarios', partido)
    for s in range(0, DURACION_PARTIDO_SEG, INTERVALO_MUESTREO_SEG):
        for region in confederaciones:
            usuarios = max(5000, AUDIENCIA_BASE.get(region, 80000) + int(azar.uniform(-15000, 25000)))
            yield (f'actividad_usuarios,partido_id={partido["codigo"]},region={region} '
                   f'usuarios_conectados={usuarios}i {partido["inicio"] + s}')


TABLAS = {
    'tracking_jugador': (BASE_EN_VIVO, lineas_tracking_jugador),
    'tracking_pelota': (BASE_EN_VIVO, lineas_tracking_pelota),
    'estadisticas_partido': (BASE_RESUMEN, lineas_estadisticas_partido),
    'actividad_usuarios': (BASE_RESUMEN, lineas_actividad_usuarios),
}


def resumir(partidos, confederaciones):
    """Cuenta puntos y series (medición + conjunto de tags) sin conectarse a InfluxDB."""
    tablas = {}
    for tabla, (base, generar) in TABLAS.items():
        puntos, series = 0, set()
        for partido in partidos:
            for linea in generar(partido, confederaciones):
                puntos += 1
                series.add(linea.split(' ', 1)[0])
        tablas[tabla] = dict(base=base, puntos=puntos, series=len(series))
    return dict(
        partidos=len(partidos),
        partidos_con_titulares=sum(1 for p in partidos if p['titulares']),
        tablas=tablas,
        puntos_totales=sum(t['puntos'] for t in tablas.values()),
        series_totales=sum(t['series'] for t in tablas.values()),
    )


def en_lotes(lineas, tamano=LOTE_LINEAS):
    lote = []
    for linea in lineas:
        lote.append(linea)
        if len(lote) == tamano:
            yield lote
            lote = []
    if lote:
        yield lote


def escribir(session, url, token, base, lineas):
    """POST /api/v3/write_lp con precisión en segundos; devuelve las líneas rechazadas tras los reintentos."""
    import requests
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    rechazadas = 0
    for lote in en_lotes(lineas):
        cuerpo = ('\n'.join(lote) + '\n').encode('utf-8')
        for _ in range(INTENTOS_POR_LOTE):
            try:
                respuesta = session.post(f'{url.rstrip("/")}/api/v3/write_lp',
                                         params={'db': base, 'precision': 'second'},
                                         data=cuerpo, headers=headers, timeout=60)
                if respuesta.status_code == 204:
                    break
            except requests.RequestException:
                pass
        else:
            rechazadas += len(lote)
    return rechazadas


def cargar(partidos, confederaciones, url, token):
    import requests
    resultado = {}
    with requests.Session() as session:
        for tabla, (base, generar) in TABLAS.items():
            enviadas = rechazadas = 0
            for partido in partidos:
                lineas = list(generar(partido, confederaciones))
                enviadas += len(lineas)
                rechazadas += escribir(session, url, token, base, lineas)
            resultado[tabla] = dict(base=base, enviadas=enviadas, rechazadas=rechazadas)
    return resultado


def exportar(partidos, confederaciones, destino):
    destino.mkdir(parents=True, exist_ok=True)
    for tabla, (_, generar) in TABLAS.items():
        for partido in partidos:
            lineas = list(generar(partido, confederaciones))
            if lineas:
                (destino / f'{tabla}_{partido["codigo"]}.lp').write_text('\n'.join(lineas) + '\n', encoding='utf-8')


def influxdb3(*argumentos, token):
    comando = ['docker', 'compose', 'exec', '-T', 'influxdb', 'influxdb3', *argumentos, '--token', token]
    return subprocess.run(comando, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def crear_bases(token):
    """Usa el contenedor `influxdb` ya iniciado; no inicia contenedores ni borra bases existentes."""
    existentes = influxdb3('show', 'databases', token=token)
    creadas = []
    for base, retencion in RETENCION.items():
        if re.search(rf'\b{base}\b', existentes):
            continue
        opciones = ['--retention-period', retencion] if retencion else []
        influxdb3('create', 'database', base, *opciones, token=token)
        creadas.append(base)
    return dict(creadas=creadas, existentes=[b for b in RETENCION if b not in creadas])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-dir', type=Path, default=DATA / 'import')
    parser.add_argument('--calendario', type=Path, default=DATA / 'fixture-calendario.json')
    parser.add_argument('--alineaciones', type=Path, action='append',
                        help='Lote con el formato de cargar_alineaciones.py; repetible. '
                             'Por defecto data/fixture/alineaciones-argentina-demo.json')
    parser.add_argument('--partido', action='append', help='Limita a uno o más partidos, p. ej. P-001')
    accion = parser.add_mutually_exclusive_group()
    accion.add_argument('--solo-validar', action='store_true', help='Genera en memoria y cuenta puntos y series sin conectar a InfluxDB')
    accion.add_argument('--crear-bases', action='store_true', help=f'Crea {BASE_EN_VIVO} (7d) y {BASE_RESUMEN} (sin vencimiento) si faltan')
    accion.add_argument('--exportar', type=Path, metavar='DIR', help='Escribe archivos .lp por tabla y partido sin conectar a InfluxDB')
    args = parser.parse_args()

    partidos, confederaciones = preparar(args.import_dir, args.calendario,
                                         args.alineaciones or [DATA / 'alineaciones-argentina-demo.json'])
    if args.partido:
        desconocidos = set(args.partido) - {p['codigo'] for p in partidos}
        if desconocidos:
            parser.error(f'Partidos inexistentes: {sorted(desconocidos)}')
        partidos = [p for p in partidos if p['codigo'] in args.partido]

    if args.solo_validar:
        print(json.dumps(resumir(partidos, confederaciones), indent=2))
        return
    if args.exportar:
        exportar(partidos, confederaciones, args.exportar)
        print(json.dumps(dict(exportado_en=str(args.exportar), partidos=len(partidos))))
        return

    from app.adapters.influx_adapter import influx_adapter
    from app.config.settings import settings
    token = influx_adapter._resolve_token()
    if args.crear_bases:
        if not token:
            parser.error('Falta el token de InfluxDB (INFLUX_TOKEN o .influxdb3-token)')
        print(json.dumps(crear_bases(token)))
        return
    resultado = cargar(partidos, confederaciones, settings.influx_url, token)
    print(json.dumps(resultado, indent=2))
    if any(t['rechazadas'] for t in resultado.values()):
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f'influxdb3 terminó con código {exc.returncode}. Verificar que el servicio influxdb esté iniciado.', file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError) as exc:
        print(f'Carga interrumpida: {exc}', file=sys.stderr)
        sys.exit(1)
