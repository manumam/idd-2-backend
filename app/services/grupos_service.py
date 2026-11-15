"""Clasificación sin acumulaciones: corregir un resultado reemplaza la tabla."""
import hashlib
import logging
from pydantic import ValidationError
from app.adapters import mongo_adapter, redis_adapter
from app.config.settings import settings
from app.core.exceptions import ResourceNotFoundError
from app.core.exceptions import DatabaseUnavailableError
from app.schemas.grupos import Grupo, GruposResponse, PosicionGrupo, PosicionesResponse
from app.schemas.fixture import PartidoFixture

logger = logging.getLogger(__name__)


def listar_grupos() -> GruposResponse:
    return GruposResponse(items=[Grupo(codigo=d['_id'], **{k: v for k, v in d.items() if k != '_id'})
                                 for d in mongo_adapter.list_grupos()])


def calcular_posiciones(grupo: Grupo, partidos: list[PartidoFixture]) -> PosicionesResponse:
    tabla = {e.codigo: PosicionGrupo(posicion=0, equipo=e) for e in grupo.equipos}
    pares = set()
    for partido in partidos:
        if partido.grupo != grupo.codigo or partido.fase != 'Grupos':
            raise ValueError('Partido ajeno al grupo')
        if not partido.local or not partido.visitante:
            raise ValueError('Grupo con participantes sin resolver')
        local, visitante = partido.local.codigo, partido.visitante.codigo
        if local not in tabla or visitante not in tabla or local == visitante:
            raise ValueError('Participantes inconsistentes')
        par = frozenset((local, visitante))
        if par in pares:
            raise ValueError('Cruce de grupo duplicado')
        pares.add(par)
        if partido.estado != 'finalizado':
            continue
        resultado = partido.resultado
        for propio, gf, gc in ((local, resultado.goles_local, resultado.goles_visitante),
                               (visitante, resultado.goles_visitante, resultado.goles_local)):
            fila = tabla[propio]
            fila.jugados += 1
            fila.goles_favor += gf
            fila.goles_contra += gc
            fila.diferencia_gol = fila.goles_favor - fila.goles_contra
            if gf > gc:
                fila.ganados += 1
                fila.puntos += grupo.reglas.victoria
            elif gf == gc:
                fila.empatados += 1
                fila.puntos += grupo.reglas.empate
            else:
                fila.perdidos += 1
                fila.puntos += grupo.reglas.derrota
    orden = {code: i for i, code in enumerate(grupo.reglas.orden_desempate)}
    filas = sorted(tabla.values(), key=lambda f: (-f.puntos, -f.diferencia_gol, -f.goles_favor, orden[f.equipo.codigo]))
    for i, fila in enumerate(filas, 1):
        fila.posicion = i
    esperados = len(tabla) * (len(tabla) - 1) // 2
    return PosicionesResponse(grupo=grupo, items=filas, partidos=partidos,
        completa=len(partidos) == esperados and all(p.estado == 'finalizado' for p in partidos))


def consultar_posiciones(codigo: str) -> PosicionesResponse:
    documento = mongo_adapter.find_grupo(codigo)
    if documento is None:
        raise ResourceNotFoundError('GRUPO_NO_ENCONTRADO', 'No existe el grupo solicitado.')
    grupo = Grupo(codigo=documento['_id'], **{k: v for k, v in documento.items() if k != '_id'})
    partidos = [PartidoFixture(codigo=d['_id'], **{k: v for k, v in d.items() if k != '_id'})
                for d in mongo_adapter.list_partidos_grupo(codigo)]
    # La clave depende de TODAS las entradas. Un cierre, corrección o cambio de
    # reglas deja de referenciar la versión anterior incluso con escritores externos.
    payload = grupo.model_dump_json() + ''.join(p.model_dump_json() for p in partidos)
    key = f'grupos:v1:{codigo}:{hashlib.sha256(payload.encode()).hexdigest()}'
    try:
        cached = redis_adapter.get_cache(key)
        if cached is not None:
            return PosicionesResponse.model_validate_json(cached)
    except (DatabaseUnavailableError, ValidationError, UnicodeError):
        logger.warning('Caché de posiciones no disponible o inválida')
    respuesta = calcular_posiciones(grupo, partidos)
    try:
        redis_adapter.set_cache(key, respuesta.model_dump_json(), settings.fixture_cache_ttl_seconds)
    except DatabaseUnavailableError:
        logger.warning('No se pudo cachear la clasificación')
    return respuesta
