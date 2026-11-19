"""Clasificación sin acumulaciones: corregir un resultado reemplaza la tabla."""
from app.adapters import mongo_adapter
from app.core.exceptions import ResourceNotFoundError
from app.schemas.grupos import Grupo, GruposResponse, PosicionGrupo, PosicionesResponse
from app.schemas.fixture import PartidoFixture
from app.services.cache_partidos import clave_posiciones, guardar_cache, leer_cache


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
    key = clave_posiciones(codigo)
    cached = leer_cache(key, PosicionesResponse)
    if cached is not None:
        return cached
    documento = mongo_adapter.find_grupo(codigo)
    if documento is None:
        raise ResourceNotFoundError('GRUPO_NO_ENCONTRADO', 'No existe el grupo solicitado.')
    grupo = Grupo(codigo=documento['_id'], **{k: v for k, v in documento.items() if k != '_id'})
    partidos = [PartidoFixture(codigo=d['_id'], **{k: v for k, v in d.items() if k != '_id'})
                for d in mongo_adapter.list_partidos_grupo(codigo)]
    respuesta = calcular_posiciones(grupo, partidos)
    guardar_cache(key, respuesta)
    return respuesta
