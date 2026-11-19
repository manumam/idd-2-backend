"""Generación de puntos para InfluxDB sin conectarse al motor."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cargar_influx', ROOT / 'scripts/cargar_influx.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


@pytest.fixture(scope='module')
def torneo():
    return seed.preparar()


def partido(torneo, codigo):
    return next(p for p in torneo[0] if p['codigo'] == codigo)


def parsear(linea):
    serie, campos, instante = linea.split(' ')
    medicion, *tags = serie.split(',')
    return medicion, dict(t.split('=') for t in tags), dict(c.split('=') for c in campos.split(',')), int(instante)


def test_lee_partidos_sedes_y_horarios_del_backend(torneo):
    partidos, confederaciones = torneo
    assert len(partidos) == 127
    assert confederaciones == ['AFC', 'CAF', 'CONCACAF', 'CONMEBOL', 'OFC', 'UEFA']
    p001 = partido(torneo, 'P-001')
    assert p001['equipos'] == ['URU', 'KSA'] and p001['sede'] == 'S-01'
    assert p001['inicio'] == 1907172000  # 2030-06-08T18:00:00Z de fixture-calendario.json


def test_tracking_jugador_solo_con_titulares_versionados(torneo):
    con_titulares = {p['codigo']: p['titulares'] for p in torneo[0] if p['titulares']}
    assert set(con_titulares) == {'P-002', 'P-051', 'P-083'}
    assert all(len(t) == 11 and {e for _, e in t} == {'ARG'} for t in con_titulares.values())
    assert list(seed.lineas_tracking_jugador(partido(torneo, 'P-001'))) == []


def test_line_protocol_conserva_tags_fields_tipos_y_segundos(torneo):
    p = partido(torneo, 'P-002')
    medicion, tags, campos, instante = parsear(next(seed.lineas_estadisticas_partido(p)))
    assert medicion == 'estadisticas_partido'
    assert tags == {'partido_id': 'P-002', 'equipo_id': p['equipos'][0], 'sede_id': p['sede']}
    assert set(campos) == {'posesion_pct', 'tiros_acumulados', 'pases_intervalo'}
    assert campos['tiros_acumulados'].endswith('i') and campos['pases_intervalo'].endswith('i')
    assert instante == p['inicio']
    medicion, tags, campos, _ = parsear(next(seed.lineas_tracking_jugador(p)))
    assert (medicion, set(tags), set(campos)) == (
        'tracking_jugador', {'partido_id', 'equipo_id', 'jugador_id'}, {'x_m', 'y_m', 'velocidad_kmh', 'distancia_acum_m'})
    medicion, tags, campos, _ = parsear(next(seed.lineas_actividad_usuarios(p, torneo[1])))
    assert (medicion, set(tags), campos['usuarios_conectados'][-1]) == ('actividad_usuarios', {'partido_id', 'region'}, 'i')


def test_valores_plausibles_y_contadores_monotonos(torneo):
    p = partido(torneo, 'P-002')
    jugador = [parsear(l) for l in seed.lineas_tracking_jugador(p)]
    assert all(0 <= float(c['velocidad_kmh']) <= 36 for _, _, c, _ in jugador)
    odometro = [float(c['distancia_acum_m']) for _, t, c, _ in jugador if t['jugador_id'] == 'ARG-10']
    assert odometro == sorted(odometro) and 15000 <= odometro[-1] <= 30000
    for equipo in p['equipos']:
        tiros = [int(c['tiros_acumulados'][:-1]) for _, t, c, _ in map(parsear, seed.lineas_estadisticas_partido(p)) if t['equipo_id'] == equipo]
        assert tiros == sorted(tiros)
    posesion = [float(c['posesion_pct']) for _, _, c, _ in map(parsear, seed.lineas_estadisticas_partido(p))]
    assert all(abs(a + b - 100.0) < 0.01 for a, b in zip(posesion[::2], posesion[1::2]))


def test_generacion_determinista_por_partido(torneo):
    p = partido(torneo, 'P-010')
    assert list(seed.lineas_tracking_pelota(p)) == list(seed.lineas_tracking_pelota(dict(p)))
    otro = partido(torneo, 'P-011')
    assert next(seed.lineas_tracking_pelota(p)).split(' ')[1] != next(seed.lineas_tracking_pelota(otro)).split(' ')[1]


def test_resumen_cuenta_puntos_y_series_del_modelo(torneo):
    partidos, confederaciones = torneo
    resumen = seed.resumir([partido(torneo, 'P-002'), partido(torneo, 'P-003')], confederaciones)
    tablas = resumen['tablas']
    assert tablas['tracking_pelota'] == dict(base='fixture2030_en_vivo', puntos=2 * 5400, series=2)
    assert tablas['tracking_jugador'] == dict(base='fixture2030_en_vivo', puntos=11 * 5400, series=11)
    assert tablas['estadisticas_partido'] == dict(base='fixture2030_resumen', puntos=2 * 2 * 1080, series=4)
    assert tablas['actividad_usuarios'] == dict(base='fixture2030_resumen', puntos=2 * 6 * 1080, series=12)


def test_rechaza_alineacion_de_otra_plaza(tmp_path, torneo):
    lote = json.loads((ROOT / 'data/fixture/alineaciones-argentina-demo.json').read_text())
    lote['partidos'][0]['partido'] = 'P-001'
    archivo = tmp_path / 'alineaciones.json'
    archivo.write_text(json.dumps(lote))
    with pytest.raises(ValueError, match='plaza'):
        seed.preparar(alineaciones=[archivo])


def test_rechaza_tags_que_romperian_el_line_protocol():
    with pytest.raises(ValueError, match='tag'):
        seed._tag('Copa America')


def test_escribe_en_lotes_con_precision_en_segundos_y_reintenta():
    session = MagicMock()
    session.post.side_effect = [MagicMock(status_code=204), MagicMock(status_code=500), MagicMock(status_code=204)]
    lineas = [f'tracking_pelota,partido_id=P-001 x_m=1.00 {i}' for i in range(seed.LOTE_LINEAS + 1)]
    rechazadas = seed.escribir(session, 'http://influx:8181/', 'secreto', 'fixture2030_en_vivo', lineas)
    assert rechazadas == 0
    assert session.post.call_count == 3
    _, kwargs = session.post.call_args
    assert session.post.call_args[0][0] == 'http://influx:8181/api/v3/write_lp'
    assert kwargs['params'] == {'db': 'fixture2030_en_vivo', 'precision': 'second'}
    assert kwargs['headers'] == {'Authorization': 'Bearer secreto'}
    assert kwargs['data'].decode().count('\n') == 1


def test_lote_rechazado_tras_los_reintentos_se_informa():
    session = MagicMock()
    session.post.return_value = MagicMock(status_code=400)
    assert seed.escribir(session, 'http://influx:8181', None, 'fixture2030_resumen', ['a', 'b']) == 2
    assert session.post.call_count == seed.INTENTOS_POR_LOTE


def test_crear_bases_respeta_retencion_y_no_recrea_existentes(monkeypatch):
    llamadas = []
    def influxdb3(*argumentos, token):
        llamadas.append(argumentos)
        return 'fixture2030_resumen\n' if argumentos[0] == 'show' else ''
    monkeypatch.setattr(seed, 'influxdb3', influxdb3)
    assert seed.crear_bases('secreto') == dict(creadas=['fixture2030_en_vivo'], existentes=['fixture2030_resumen'])
    assert llamadas[1] == ('create', 'database', 'fixture2030_en_vivo', '--retention-period', '7d')
