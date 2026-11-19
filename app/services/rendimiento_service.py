"""Rendimiento individual: eventos, tracking confirmado y cierres atómicos por generación."""
import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.adapters import influx_adapter, mongo_adapter, redis_adapter
from app.core.exceptions import BaseAppException, DatabaseUnavailableError, ResourceNotFoundError
from app.schemas.alineaciones import Alineaciones
from app.schemas.partidos import EventoResponse, JugadorRef
from app.schemas.rendimiento import (
    AcumuladosJugadorResponse, ControlTracking, MetricasJugador, RendimientoResponse,
)
from app.services.comparacion_service import _base, instante
from app.services.partidos_service import _detalle_documento, _partido_no_encontrado

logger = logging.getLogger(__name__)
DEPORTIVAS = ('goles', 'asistencias', 'tarjetas_amarillas', 'tarjetas_rojas')
FISICAS = ('distancia_m', 'velocidad_max_kmh')


def huella_jugadores(doc):
    fields = ('fecha_hora', 'estado', 'local', 'visitante', 'resultado', 'eventos', 'reloj',
              'alineaciones', 'tracking_control')
    return hashlib.sha256(json.dumps({k: doc.get(k) for k in fields}, sort_keys=True, default=str).encode()).hexdigest()


def _jugador(codigo):
    doc = mongo_adapter.find_jugador(codigo)
    if doc is None:
        raise ResourceNotFoundError('JUGADOR_NO_ENCONTRADO', f"No existe el jugador '{codigo}'.")
    return JugadorRef(codigo=codigo, nombre=f"{doc['nombre']} {doc.get('apellido', '')}".strip()), dict(
        codigo=doc['equipo']['_id'], nombre=doc['equipo']['nombre'])


def participantes(doc, partido):
    """Solo las convocatorias de las plazas actuales; nunca hereda jugadores obsoletos."""
    refs = {}
    try:
        alineaciones = Alineaciones.model_validate(doc.get('alineaciones') or {})
        for lado in ('local', 'visitante'):
            equipo = getattr(partido, lado)
            convocatoria = getattr(alineaciones, lado)
            if convocatoria and equipo and convocatoria.equipo.codigo == equipo.codigo:
                refs.update({j.codigo: JugadorRef(codigo=j.codigo, nombre=j.nombre)
                             for j in convocatoria.titulares + convocatoria.suplentes})
        if not partido.requiere_revision and partido.estado != 'proximo':
            for raw in doc.get('eventos', []):
                evento = EventoResponse.model_validate(raw)
                if evento.equipo.codigo in {e.codigo for e in (partido.local, partido.visitante) if e}:
                    refs.update({p.jugador.codigo: JugadorRef(**p.jugador.model_dump()) for p in evento.protagonistas})
    except (ValidationError, TypeError, ValueError) as exc:
        raise BaseAppException('RENDIMIENTO_INVALIDO', 'Las convocatorias o los eventos requieren revisión.') from exc
    return refs


def _control(doc, partido):
    control = ControlTracking.model_validate(doc['tracking_control'])
    inicio = instante(doc['fecha_hora'])
    if not partido.reloj:
        raise ValueError('Sin reloj de ingesta')
    fin = inicio + timedelta(minutes=partido.reloj.minuto + partido.reloj.adicional)
    equipos = {e.codigo for e in (partido.local, partido.visitante) if e}
    alineaciones = Alineaciones.model_validate(doc.get('alineaciones') or {})
    suplentes = set()
    activos = set()
    for lado in ('local', 'visitante'):
        convocatoria = getattr(alineaciones, lado)
        if convocatoria and convocatoria.equipo.codigo in equipos:
            suplentes.update(j.codigo for j in convocatoria.suplentes)
            activos.update(j.codigo for j in convocatoria.titulares)
    for raw in doc.get('eventos', []):
        evento = EventoResponse.model_validate(raw)
        if evento.tipo in ('gol', 'autogol', 'cambio'):
            activos.update(p.jugador.codigo for p in evento.protagonistas)
    for codigo, intervalos in control.jugadores.items():
        if codigo.split('-')[0] not in equipos:
            raise ValueError('Tracking de otra selección')
        if any(i.desde < inicio or i.hasta > fin for i in intervalos):
            raise ValueError('Tracking fuera del intervalo confirmado del partido')
        if not intervalos and (codigo not in suplentes or codigo in activos):
            raise ValueError('Solo un suplente sin participación admite cobertura vacía')
    return control


def agregar_tracking(filas, intervalo, jugador, equipo):
    """Resta extremos del odómetro, conserva base no cero y rechaza huecos/resets."""
    if len(filas) != intervalo.muestras:
        raise ValueError('Tracking incompleto o truncado')
    puntos = sorted(filas, key=lambda f: instante(f['time']))
    base = anterior = None
    maxima = 0.
    for n, fila in enumerate(puntos):
        if fila['jugador_id'] != jugador or fila['equipo_id'] != equipo:
            raise ValueError('Tracking de otro participante')
        if instante(fila['time']) != intervalo.desde + timedelta(seconds=n):
            raise ValueError('Hueco o duplicación temporal')
        distancia, velocidad = fila['distancia_acum_m'], fila['velocidad_kmh']
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
               for v in (distancia, velocidad)):
            raise ValueError('Métrica física inválida')
        if anterior is not None and distancia < anterior:
            raise ValueError('Odómetro reiniciado dentro del intervalo')
        if base is None:
            base = distancia
        anterior, maxima = distancia, max(maxima, velocidad)
    return anterior - base, maxima


def _deportivas(doc, jugador, equipo, partido):
    respuesta = RendimientoResponse(partido=partido.codigo, jugador=jugador, equipo=equipo,
        estado=partido.estado, reloj=partido.reloj,
        actualizado_en=instante(doc['actualizado_en']) if doc.get('actualizado_en') else None,
        consolidacion='sin_datos' if partido.estado == 'proximo' else 'pendiente')
    if partido.estado == 'proximo' or partido.requiere_revision:
        return respuesta
    # Reutiliza la validación de cronología única, participantes y marcador del caso 8.
    base = _base(doc)
    if base.advertencias:
        respuesta.advertencias.extend(base.advertencias)
        return respuesta
    for campo in DEPORTIVAS:
        setattr(respuesta.metricas, campo, 0)
    for raw in doc['eventos']:
        evento = EventoResponse.model_validate(raw)
        for p in evento.protagonistas:
            if p.jugador.codigo != jugador.codigo:
                continue
            campo = None
            if evento.tipo == 'gol':
                campo = 'goles' if p.rol == 'autor' else 'asistencias'
            elif evento.tipo in ('tarjeta_amarilla', 'tarjeta_roja'):
                campo = 'tarjetas_amarillas' if evento.tipo == 'tarjeta_amarilla' else 'tarjetas_rojas'
            if campo:
                setattr(respuesta.metricas, campo, getattr(respuesta.metricas, campo) + 1)
    return respuesta


def _fisicas(doc, respuesta):
    try:
        control = _control(doc, _detalle_documento(doc))
        intervalos = control.jugadores[respuesta.jugador.codigo]
        distancia, maxima = 0., 0.
        for i in intervalos:
            filas = influx_adapter.find_tracking_jugador(doc['_id'], respuesta.jugador.codigo,
                respuesta.equipo.codigo, i.desde.isoformat(), i.hasta.isoformat())
            d, v = agregar_tracking(filas, i, respuesta.jugador.codigo, respuesta.equipo.codigo)
            distancia += d
            maxima = max(maxima, v)
        respuesta.metricas.distancia_m = round(distancia, 2)
        respuesta.metricas.velocidad_max_kmh = round(maxima, 2)
        if not respuesta.advertencias:
            respuesta.consolidacion = 'provisional'
    except DatabaseUnavailableError as exc:
        if exc.status_code == 500:
            raise
        respuesta.advertencias.append('Tracking no disponible; se conservan las estadísticas deportivas.')
    except (KeyError, ValueError, TypeError):
        respuesta.advertencias.append('Tracking ausente, incompleto o pendiente de confirmar.')
    return respuesta


def _final(doc, respuesta):
    manifiesto = doc.get('jugadores_finales') or {}
    if manifiesto.get('huella') != huella_jugadores(doc) or respuesta.jugador.codigo not in manifiesto.get('jugadores', []):
        return None
    try:
        generacion = manifiesto['generacion']
    except KeyError:
        return None
    raw = mongo_adapter.find_resumen_jugador(doc['_id'], generacion, respuesta.jugador.codigo)
    try:
        final = RendimientoResponse.model_validate(raw['resumen'])
        if (final.partido != respuesta.partido or final.jugador != respuesta.jugador
            or final.equipo != respuesta.equipo or final.estado != 'finalizado'
            or final.consolidacion != 'completa' or final.advertencias or respuesta.advertencias
            or final.reloj != respuesta.reloj
            or any(getattr(final.metricas, k) is None for k in DEPORTIVAS + FISICAS)
            or any(getattr(final.metricas, k) != getattr(respuesta.metricas, k) for k in DEPORTIVAS)):
            return None
        return final
    except (ValidationError, KeyError, TypeError):
        return None


def _consultar(doc, jugador, equipo):
    partido = _detalle_documento(doc)
    refs = participantes(doc, partido)
    # Un control confirmado también puede identificar jugadores sin convocatoria histórica.
    try:
        control = _control(doc, partido)
        conocido = jugador.codigo in control.jugadores
    except (KeyError, ValueError, TypeError):
        conocido = False
    equipos = {e.codigo for e in (partido.local, partido.visitante) if e}
    if equipo['codigo'] not in equipos or (jugador.codigo not in refs and not conocido):
        raise ResourceNotFoundError('JUGADOR_NO_CONVOCADO', 'El jugador no está registrado en este encuentro.')
    jugador = refs.get(jugador.codigo, jugador)
    respuesta = _deportivas(doc, jugador, equipo, partido)
    if respuesta.estado == 'proximo':
        return respuesta
    if respuesta.estado == 'finalizado':
        final = _final(doc, respuesta)
        if final:
            return final
        respuesta.advertencias.append('Resumen individual final pendiente de consolidación o reproceso.')
        return respuesta  # Los GET finales y acumulados nunca leen Influx.
    key = f'rendimiento:v1:{doc["_id"]}:{jugador.codigo}:{huella_jugadores(doc)}'
    try:
        cached = redis_adapter.get_cache(key)
        if cached:
            parsed = RendimientoResponse.model_validate_json(cached)
            if parsed.partido == respuesta.partido and parsed.jugador == respuesta.jugador and parsed.equipo == respuesta.equipo:
                return parsed
    except (DatabaseUnavailableError, ValidationError, ValueError, TypeError):
        logger.warning('Caché individual no disponible o inválida')
    respuesta = _fisicas(doc, respuesta)
    if respuesta.consolidacion == 'provisional':
        try:
            redis_adapter.set_cache(key, respuesta.model_dump_json(), 5)
        except DatabaseUnavailableError:
            logger.warning('No se pudo cachear el rendimiento')
    return respuesta


def obtener_rendimiento(codigo, jugador_codigo):
    jugador, equipo = _jugador(jugador_codigo)
    doc = mongo_adapter.find_estadisticas(codigo)
    if doc is None:
        raise _partido_no_encontrado(codigo)
    return _consultar(doc, jugador, equipo)


def obtener_acumulados(codigo):
    jugador, equipo = _jugador(codigo)
    documentos = mongo_adapter.list_partidos_jugador(codigo)
    version = hashlib.sha256(json.dumps([
        (d['_id'], huella_jugadores(d), d.get('jugadores_finales')) for d in documentos
    ], sort_keys=True, default=str).encode()).hexdigest()
    key = f'acumulados:v1:{codigo}:{version}'
    try:
        cached = redis_adapter.get_cache(key)
        if cached:
            parsed = AcumuladosJugadorResponse.model_validate_json(cached)
            if parsed.jugador == jugador and parsed.equipo.model_dump() == equipo:
                return parsed
    except (DatabaseUnavailableError, ValidationError, ValueError, TypeError):
        logger.warning('Caché de acumulados no disponible o inválida')
    partidos = []
    for doc in documentos:
        try:
            # En vivo: solo eventos. Los acumulados no necesitan tracking crudo.
            partido = _detalle_documento(doc)
            refs = participantes(doc, partido)
            if equipo['codigo'] not in {e.codigo for e in (partido.local, partido.visitante) if e}:
                continue
            if codigo not in refs and codigo not in (doc.get('tracking_control') or {}).get('jugadores', {}):
                continue
            if partido.estado == 'en_vivo':
                r = _deportivas(doc, refs.get(codigo, jugador), equipo, partido)
                if not r.advertencias:
                    r.consolidacion = 'provisional'
            else:
                r = _consultar(doc, jugador, equipo)
            if r.estado != 'proximo':
                partidos.append(r)
        except ResourceNotFoundError:
            continue  # Una corrección de plazas no hereda los acumulados previos.
    metricas = MetricasJugador()
    for campo in DEPORTIVAS + FISICAS:
        valores = [getattr(p.metricas, campo) for p in partidos]
        if valores and all(v is not None for v in valores):
            setattr(metricas, campo, max(valores) if campo == 'velocidad_max_kmh' else sum(valores))
    completos = sum(p.consolidacion == 'completa' for p in partidos)
    estado = ('sin_datos' if not partidos else 'completa' if completos == len(partidos)
              else 'pendiente' if any(p.consolidacion == 'pendiente' for p in partidos) else 'provisional')
    respuesta = AcumuladosJugadorResponse(jugador=jugador, equipo=equipo, consolidacion=estado,
        metricas=metricas, partidos=partidos, partidos_consolidados=completos,
        partidos_pendientes=len(partidos) - completos,
        advertencias=['Las métricas incompletas se muestran sin total; consultar el detalle por partido.']
            if any(getattr(metricas, c) is None for c in DEPORTIVAS + FISICAS) and partidos else [])
    try:
        redis_adapter.set_cache(key, respuesta.model_dump_json(), 5)
    except DatabaseUnavailableError:
        logger.warning('No se pudo cachear el acumulado')
    return respuesta


def consolidar_jugadores(codigo):
    doc = mongo_adapter.find_estadisticas(codigo)
    if doc is None:
        raise _partido_no_encontrado(codigo)
    partido = _detalle_documento(doc)
    if partido.estado != 'finalizado' or partido.requiere_revision:
        raise ValueError('Solo se consolida un partido finalizado con participantes vigentes')
    control = _control(doc, partido)
    if not control.completa:
        raise ValueError('La ingesta de tracking todavía no está cerrada')
    refs = participantes(doc, partido)
    codigos = sorted(set(refs) | set(control.jugadores))
    if not codigos:
        raise ValueError('No hay participantes confirmados')
    generacion, resumenes = uuid4().hex, []
    ahora = datetime.now(timezone.utc)
    for codigo_jugador in codigos:
        jugador, equipo = _jugador(codigo_jugador)
        jugador = refs.get(codigo_jugador, jugador)
        respuesta = _fisicas(doc, _deportivas(doc, jugador, equipo, partido))
        if respuesta.advertencias or any(getattr(respuesta.metricas, c) is None for c in DEPORTIVAS + FISICAS):
            raise ValueError(f'Entradas incompletas para {codigo_jugador}')
        respuesta.consolidacion, respuesta.actualizado_en = 'completa', ahora
        resumenes.append(dict(_id=f'{codigo}:{generacion}:{codigo_jugador}', partido_id=codigo,
            jugador_id=codigo_jugador, generacion=generacion, resumen=respuesta.model_dump(mode='json')))
    manifiesto = dict(huella=huella_jugadores(doc), generacion=generacion, jugadores=codigos)
    if not mongo_adapter.publicar_resumenes_jugadores(codigo, doc, manifiesto, resumenes):
        raise ValueError('El partido cambió durante el cierre; reintentar')
    try:
        redis_adapter.delete_cache_matching('rendimiento:v1:*')
        redis_adapter.delete_cache_matching('acumulados:v1:*')
    except DatabaseUnavailableError:
        logger.warning('Caché individual no disponible; las claves incluyen las entradas actuales')
    return [r['resumen'] for r in resumenes]
