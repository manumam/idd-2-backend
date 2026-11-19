"""Ingesta local del simulador: un tick confirma eventos, marcador y reloj juntos."""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.adapters import mongo_adapter
from app.schemas.partidos import EventoResponse, RelojPartido
from app.services.fixture_service import invalidar_fixture
from app.services.partidos_service import _detalle_documento, _partido_no_encontrado


class TickPartido(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reloj: RelojPartido
    eventos: list[EventoResponse] = Field(default_factory=list, max_length=200)
    finalizado: bool = False


def aplicar_tick(codigo: str, tick: TickPartido) -> bool:
    """Sin reinicios ni correcciones: IDs repetidos se conservan; conflicto concurrente se informa."""
    documento = mongo_adapter.find_eventos(codigo)
    if documento is None:
        raise _partido_no_encontrado(codigo)
    partido = _detalle_documento(documento)
    if partido.requiere_revision or not partido.local or not partido.visitante:
        raise ValueError("El partido necesita participantes definidos y un resultado válido")
    for lado in ("local", "visitante"):
        if documento.get(lado) != getattr(partido, lado).model_dump():
            raise ValueError("Actualizar las plazas persistidas antes de simular el cruce")
    anteriores = [EventoResponse.model_validate(e) for e in documento.get("eventos", [])]
    por_id = {e.codigo: e for e in anteriores}
    if len(por_id) != len(anteriores):
        raise ValueError("La cronología contiene IDs duplicados")
    reloj = (tick.reloj.minuto, tick.reloj.adicional)
    nuevos = []
    equipos = {e.codigo: e for e in (partido.local, partido.visitante)}
    for evento in tick.eventos:
        if evento.codigo in por_id:
            # Protección básica para reenvíos. Las correcciones se hacen fuera de este simulador.
            if evento != por_id[evento.codigo]:
                raise ValueError("El ID ya existe con otro contenido")
            continue
        if evento.equipo.codigo not in equipos:
            raise ValueError("El equipo del evento no juega este partido")
        if evento.equipo.model_dump() != equipos[evento.equipo.codigo].model_dump():
            raise ValueError("La referencia de selección no coincide con el partido")
        if (evento.minuto, evento.adicional) > reloj:
            raise ValueError("El evento ocurre después del reloj informado")
        for protagonista in evento.protagonistas:
            jugador = mongo_adapter.find_jugador(protagonista.jugador.codigo)
            if jugador is None or jugador["equipo"]["_id"] != evento.equipo.codigo:
                raise ValueError("Jugador inexistente o de otra selección")
            nombre = f"{jugador['nombre']} {jugador.get('apellido', '')}".strip()
            if protagonista.jugador.nombre != nombre:
                raise ValueError("El nombre del jugador no coincide con el catálogo")
        por_id[evento.codigo] = evento
        nuevos.append(evento)
    if partido.estado == "finalizado":
        if nuevos or not tick.finalizado or tick.reloj != partido.reloj:
            raise ValueError("No se puede modificar un partido finalizado")
        return False
    if partido.reloj and reloj < (partido.reloj.minuto, partido.reloj.adicional):
        # Permite el paso de 45+N al inicio del segundo tiempo y de 90+N a prórroga.
        transiciones = {("primer_tiempo", "entretiempo"), ("entretiempo", "segundo_tiempo"),
            ("primer_tiempo", "segundo_tiempo"), ("segundo_tiempo", "prorroga_primer_tiempo"),
            ("prorroga_primer_tiempo", "descanso_prorroga"),
            ("descanso_prorroga", "prorroga_segundo_tiempo")}
        if (partido.reloj.periodo, tick.reloj.periodo) not in transiciones or tick.reloj.minuto < partido.reloj.minuto:
            raise ValueError("El reloj no puede retroceder")
    if tick.finalizado and tick.reloj.minuto < 90:
        raise ValueError("El cierre requiere al menos 90 minutos")
    resultado = partido.resultado.model_dump() if partido.resultado else {
        "goles_local": 0, "goles_visitante": 0, "penales": None}
    for evento in nuevos:
        if evento.tipo in ("gol", "autogol"):
            local = evento.equipo.codigo == partido.local.codigo
            if evento.tipo == "autogol":
                local = not local
            resultado["goles_local" if local else "goles_visitante"] += 1
    cambios = dict(eventos=[e.model_dump() for e in por_id.values()], resultado=resultado,
        estado="finalizado" if tick.finalizado else "en_vivo", reloj=tick.reloj.model_dump(),
        actualizado_en=datetime.now(timezone.utc))
    if not mongo_adapter.guardar_seguimiento(codigo, documento, cambios):
        raise ValueError("El partido cambió durante el tick; volver a consultar antes de continuar")
    # Detalle/eventos/grupos/playoffs ya versionan sus claves por las entradas actuales.
    # Las estadísticas temporales del caso 8 siguen separadas y todavía no cachean eventos.
    invalidar_fixture()
    return True
