"""Recalcula sin escrituras: las correcciones nunca propagan un resultado ajeno."""
from app.adapters import mongo_adapter
from app.schemas.fixture import PartidoFixture
from app.schemas.grupos import Grupo
from app.schemas.playoffs import Cruce, CruceResuelto, Plaza, PlayoffsResponse
from app.services.cache_partidos import PLAYOFFS_CACHE_KEY, guardar_cache, leer_cache
from app.services.grupos_service import calcular_posiciones

FASES = ['Dieciseisavos', 'Octavos', 'Cuartos', 'Semifinal', 'Final']


def validar_cruces(cruces, partidos, grupos):
    """Valida el lote entero antes de cargarlo o resolverlo; devuelve orden topológico."""
    por_id = {c.codigo: c for c in cruces}
    if len(por_id) != len(cruces) or len({(c.fase, c.orden) for c in cruces}) != len(cruces):
        raise ValueError('Cruce u orden duplicado')
    usados, destinos = set(), set()
    for c in cruces:
        if c.codigo not in partidos or partidos[c.codigo].fase != c.fase:
            raise ValueError('Partido inexistente o fase inconsistente')
        for origen in (c.local, c.visitante):
            key = origen.model_dump_json()
            if key in usados:
                raise ValueError('Plaza asignada más de una vez')
            usados.add(key)
            if origen.tipo == 'grupo' and origen.grupo not in grupos:
                raise ValueError('Grupo inexistente')
            if origen.tipo == 'ganador':
                anterior = por_id.get(origen.cruce)
                if anterior is None or FASES.index(anterior.fase) + 1 != FASES.index(c.fase):
                    raise ValueError('Dependencia inválida o ciclo entre cruces')
                destinos.add(origen.cruce)
    finales = [c for c in cruces if c.codigo not in destinos]
    if cruces and (len(finales) != 1 or finales[0].fase != 'Final'):
        raise ValueError('El cuadro debe converger en una única final')
    return sorted(cruces, key=lambda c: (FASES.index(c.fase), c.orden))


def resolver(cruces, partidos, grupos):
    ordenados = validar_cruces(cruces, partidos, grupos)
    tablas = {}
    for codigo in {o.grupo for c in cruces for o in (c.local, c.visitante) if o.tipo == 'grupo'}:
        tablas[codigo] = calcular_posiciones(grupos[codigo], [p for p in partidos.values() if p.grupo == codigo])
    resueltos = {}
    siguientes = {o.cruce: c.codigo for c in cruces for o in (c.local, c.visitante) if o.tipo == 'ganador'}

    def plaza(origen):
        equipo = None
        if origen.tipo == 'equipo':
            equipo, descripcion = origen.equipo, origen.equipo.nombre
        elif origen.tipo == 'grupo':
            tabla = tablas[origen.grupo]
            descripcion = f'{origen.posicion}.º del grupo {origen.grupo}'
            if tabla.completa:
                equipo = tabla.items[origen.posicion - 1].equipo
        else:
            descripcion = f'Ganador del partido {origen.cruce}'
            equipo = resueltos[origen.cruce].ganador
        return Plaza(origen=origen, descripcion=descripcion, equipo=equipo)

    for c in ordenados:
        local, visitante = plaza(c.local), plaza(c.visitante)
        original = partidos[c.codigo]
        coinciden = all(actual is not None and esperado is not None and actual.codigo == esperado.codigo
                        for actual, esperado in ((original.local, local.equipo), (original.visitante, visitante.equipo)))
        revision = original.estado != 'proximo' and not coinciden
        p = original.model_copy(update=dict(local=local.equipo, visitante=visitante.equipo,
            **(dict(estado='proximo', resultado=None) if revision else {})))
        ganador = None
        if p.estado == 'finalizado' and local.equipo and visitante.equipo:
            r = p.resultado
            marcador = r.penales if r.goles_local == r.goles_visitante else r
            if marcador is None or marcador.goles_local == marcador.goles_visitante or (r.penales is not None and r.goles_local != r.goles_visitante):
                revision = True
            else:
                ganador = local.equipo if marcador.goles_local > marcador.goles_visitante else visitante.equipo
        resueltos[c.codigo] = CruceResuelto(codigo=c.codigo, fase=c.fase, orden=c.orden,
            local=local, visitante=visitante, partido=p, ganador=ganador,
            siguiente=siguientes.get(c.codigo), requiere_revision=revision)
    return PlayoffsResponse(items=list(resueltos.values()))


def consultar_playoffs() -> PlayoffsResponse:
    cached = leer_cache(PLAYOFFS_CACHE_KEY, PlayoffsResponse)
    if cached is not None:
        return cached
    respuesta = calcular_playoffs()
    guardar_cache(PLAYOFFS_CACHE_KEY, respuesta)
    return respuesta


def calcular_playoffs() -> PlayoffsResponse:
    cruces = [Cruce(codigo=d['_id'], **{k:v for k,v in d.items() if k != '_id'}) for d in mongo_adapter.list_cruces()]
    if not cruces:
        return PlayoffsResponse(items=[])
    partidos = {d['_id']: PartidoFixture(codigo=d['_id'], **{k:v for k,v in d.items() if k != '_id'}) for d in mongo_adapter.list_fixture()}
    grupos = {d['_id']: Grupo(codigo=d['_id'], **{k:v for k,v in d.items() if k != '_id'}) for d in mongo_adapter.list_grupos()}
    return resolver(cruces, partidos, grupos)
