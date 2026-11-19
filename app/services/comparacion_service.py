"""Caso 8: Aggregator en vivo y consolidación explícita de equipos en MongoDB."""
import hashlib
import json
import logging
import math
from datetime import datetime, timezone

from pydantic import ValidationError
from app.adapters import mongo_adapter, influx_adapter, redis_adapter
from app.core.exceptions import DatabaseUnavailableError
from app.core.metrics import record_cache
from app.schemas.comparacion import ComparacionResponse, EstadisticasEquipo
from app.schemas.partidos import EventoResponse
from app.services.partidos_service import _detalle_documento, _partido_no_encontrado

logger = logging.getLogger(__name__)


def instante(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def huella(doc):
    campos = ('fecha_hora', 'estado', 'local', 'visitante', 'resultado', 'eventos', 'reloj', 'estadisticas_control')
    return hashlib.sha256(json.dumps({k: doc.get(k) for k in campos}, sort_keys=True, default=str).encode()).hexdigest()


def agregar_muestras(filas, control, equipos):
    """Requiere cobertura continua desde una base cero; pondera posesión por duración."""
    inicio, hasta = instante(control['inicio']), instante(control['hasta'])
    if len(filas) > 10000 or len(filas) != control['muestras']:
        raise ValueError('Cantidad de muestras incompleta')
    resultado, tiempos = {}, {}
    for equipo in equipos:
        puntos = sorted((f for f in filas if f['equipo_id'] == equipo), key=lambda f: instante(f['time']))
        if not puntos or instante(puntos[0]['time']) != inicio:
            raise ValueError('Falta la base inicial')
        anterior, tiros, pases, ponderado, duracion = inicio, 0, 0, 0., 0
        por_tiempo = {}
        for i, p in enumerate(puntos):
            hora = instante(p['time'])
            d, posesion, t, pa = p['duracion_s'], p['posesion_pct'], p['tiros_acumulados'], p['pases_intervalo']
            if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (d, posesion, t, pa)):
                raise ValueError('Muestra no numérica')
            if not 0 <= posesion <= 100 or t < tiros or pa < 0 or int(t) != t or int(pa) != pa:
                raise ValueError('Contadores inválidos')
            if i == 0:
                if d != 0 or t != 0 or pa != 0:
                    raise ValueError('La base debe ser cero')
            elif d <= 0 or (hora - anterior).total_seconds() != d:
                raise ValueError('Hueco o duplicación temporal')
            ponderado += posesion * d
            duracion += d
            pases += pa
            tiros, anterior = t, hora
            por_tiempo[hora] = posesion
        if anterior != hasta:
            raise ValueError('Falta el final del intervalo')
        resultado[equipo] = dict(posesion_pct=round(ponderado / duracion, 1) if duracion else None,
                                 tiros=int(tiros), pases=int(pases))
        tiempos[equipo] = por_tiempo
    if any(f['equipo_id'] not in equipos for f in filas):
        raise ValueError('Equipo ajeno')
    a, b = (tiempos[e] for e in equipos)
    if a.keys() != b.keys() or any(abs(a[h] + b[h] - 100) > .11 for h in a):
        raise ValueError('Posesiones incompatibles')
    return resultado


def _base(doc):
    partido = _detalle_documento(doc)
    respuesta = ComparacionResponse(partido=partido.codigo, estado=partido.estado, reloj=partido.reloj,
        consolidacion='sin_datos' if partido.estado == 'proximo' else 'pendiente',
        actualizado_en=instante(doc['actualizado_en']).isoformat() if doc.get('actualizado_en') else None,
        local=EstadisticasEquipo(equipo=partido.local) if partido.local else None,
        visitante=EstadisticasEquipo(equipo=partido.visitante) if partido.visitante else None)
    if partido.estado == 'proximo' or partido.requiere_revision:
        return respuesta
    if not respuesta.local or not respuesta.visitante:
        respuesta.advertencias.append('Participantes pendientes de definición.')
        return respuesta
    try:
        if 'eventos' not in doc:
            raise ValueError('Sin cronología')
        eventos = [EventoResponse.model_validate(e) for e in doc['eventos']]
        if len({e.codigo for e in eventos}) != len(eventos):
            raise ValueError('Eventos duplicados')
        equipos = {r.equipo.codigo: r for r in (respuesta.local, respuesta.visitante)}
        for r in equipos.values():
            r.goles = r.tarjetas_amarillas = r.tarjetas_rojas = 0
        for e in eventos:
            if e.equipo.codigo not in equipos:
                raise ValueError('Equipo ajeno')
            r = equipos[e.equipo.codigo]
            if e.tipo == 'autogol':
                r = next(v for k, v in equipos.items() if k != e.equipo.codigo)
            if e.tipo in ('gol', 'autogol'):
                r.goles += 1
            elif e.tipo == 'tarjeta_amarilla':
                r.tarjetas_amarillas += 1
            elif e.tipo == 'tarjeta_roja':
                r.tarjetas_rojas += 1
        marcador = partido.resultado
        if not marcador or (respuesta.local.goles, respuesta.visitante.goles) != (marcador.goles_local, marcador.goles_visitante):
            raise ValueError('Eventos y marcador inconsistentes')
    except (ValueError, TypeError, ValidationError):
        for r in (respuesta.local, respuesta.visitante):
            r.goles = r.tarjetas_amarillas = r.tarjetas_rojas = None
        respuesta.advertencias.append('La cronología deportiva está incompleta o requiere revisión.')
    return respuesta


def _combinar(doc, respuesta):
    control = doc.get('estadisticas_control')
    if not control or not respuesta.local or not respuesta.visitante:
        respuesta.advertencias.append('Todavía no hay muestras temporales confirmadas.')
        return respuesta
    try:
        if instante(control['inicio']) != instante(doc['fecha_hora']):
            raise ValueError('El horario de ingesta no coincide con el partido')
        if not respuesta.reloj or (instante(control['hasta']) - instante(control['inicio'])).total_seconds() != respuesta.reloj.minuto * 60 + respuesta.reloj.adicional * 60:
            raise ValueError('El avance temporal no coincide con el reloj deportivo')
        filas = influx_adapter.find_muestras(doc['_id'], control['inicio'], control['hasta'])
        valores = agregar_muestras(filas, control, [respuesta.local.equipo.codigo, respuesta.visitante.equipo.codigo])
        for r in (respuesta.local, respuesta.visitante):
            if r.goles is not None and valores[r.equipo.codigo]['tiros'] < r.goles:
                raise ValueError('Tiros incompatibles con goles')
        for r in (respuesta.local, respuesta.visitante):
            for k, v in valores[r.equipo.codigo].items():
                setattr(r, k, v)
        if not respuesta.advertencias:
            respuesta.consolidacion = 'provisional'
    except DatabaseUnavailableError as exc:
        if exc.status_code == 500:
            raise
        respuesta.advertencias.append('Las métricas temporales no están disponibles; se conservan los datos deportivos.')
    except (KeyError, ValueError, TypeError):
        respuesta.advertencias.append('Las muestras temporales están incompletas o requieren revisión.')
    return respuesta


def obtener_comparacion(codigo):
    doc = mongo_adapter.find_estadisticas(codigo)
    if doc is None:
        raise _partido_no_encontrado(codigo)
    respuesta = _base(doc)
    if respuesta.estado == 'proximo':
        return respuesta
    version = huella(doc)
    if respuesta.estado == 'finalizado':
        final = doc.get('estadisticas_finales')
        if final and final.get('huella') == version:
            try:
                guardada = ComparacionResponse.model_validate(final['resumen'])
                if (guardada.consolidacion == 'completa' and guardada.partido == codigo
                    and not guardada.advertencias and guardada.estado == 'finalizado'
                    and not respuesta.advertencias and guardada.reloj == respuesta.reloj
                    and all(a is not None and b is not None and a.equipo == b.equipo
                        and (a.goles, a.tarjetas_amarillas, a.tarjetas_rojas) == (b.goles, b.tarjetas_amarillas, b.tarjetas_rojas)
                        and all(getattr(a, k) is not None for k in ('posesion_pct', 'tiros', 'pases'))
                        for a, b in ((guardada.local, respuesta.local), (guardada.visitante, respuesta.visitante)))):
                    return guardada
            except (ValidationError, KeyError):
                pass
        respuesta.advertencias.append('Resumen final pendiente de consolidación o reproceso.')
        return respuesta  # Nunca depende de Influx para leer un final.
    # Versiona eventos, reloj e ingesta. El TTL limita cambios externos en Influx.
    key = f'estadisticas:v1:{codigo}:{version}'
    try:
        cached = redis_adapter.get_cache(key)
        if cached:
            respuesta_cache = ComparacionResponse.model_validate_json(cached)
            record_cache('estadisticas', 'hit')
            return respuesta_cache
        record_cache('estadisticas', 'miss')
    except (DatabaseUnavailableError, ValidationError, ValueError, TypeError):
        logger.warning('Caché de estadísticas no disponible o inválida')
        record_cache('estadisticas', 'error')
    respuesta = _combinar(doc, respuesta)
    if respuesta.consolidacion == 'provisional':
        try:
            redis_adapter.set_cache(key, respuesta.model_dump_json(), 5)
        except DatabaseUnavailableError:
            logger.warning('No se pudo cachear la comparación')
    return respuesta


def consolidar(codigo):
    doc = mongo_adapter.find_estadisticas(codigo)
    if doc is None:
        raise _partido_no_encontrado(codigo)
    respuesta = _base(doc)
    if respuesta.estado != 'finalizado':
        raise ValueError('Solo se consolida un partido finalizado')
    respuesta = _combinar(doc, respuesta)
    if respuesta.advertencias or not doc.get('estadisticas_control', {}).get('completa'):
        raise ValueError('Consolidación pendiente: faltan entradas confirmadas')
    respuesta.consolidacion = 'completa'
    respuesta.actualizado_en = datetime.now(timezone.utc).isoformat()
    cambios = {'estadisticas_finales': {'huella': huella(doc), 'resumen': respuesta.model_dump(mode='json')}}
    if not mongo_adapter.guardar_estadisticas(codigo, doc, cambios):
        raise ValueError('El partido cambió durante la consolidación; reintentar')
    return respuesta
