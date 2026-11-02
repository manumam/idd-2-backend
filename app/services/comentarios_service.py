"""Lectura por partición y cursor timeuuid, sin escanear otras ventanas."""

from datetime import datetime, timezone
from uuid import UUID

from app.adapters import cassandra_adapter
from app.core.exceptions import InvalidRequestError
from app.schemas.comentarios import Comentario, ComentariosPagina


def listar_comentarios(partido: str, bloque: str, limit: int, cursor: str | None) -> ComentariosPagina:
    try:
        instante = datetime.strptime(bloque, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if instante.minute % 5 or instante.second:
            raise ValueError()
        ultimo = UUID(cursor) if cursor is not None else None
        if ultimo is not None and ultimo.version != 1:
            raise ValueError()
    except ValueError:
        raise InvalidRequestError("El bloque debe ser UTC múltiplo de 5 minutos y el cursor un UUID versión 1.")
    filas = cassandra_adapter.list_comentarios(partido, instante, limit + 1, ultimo)
    pagina = filas[:limit]
    return ComentariosPagina(
        partido=partido, bloque=bloque,
        items=[Comentario(
            comentarioId=str(f["comentario_id"]), usuarioId=f["usuario_id"],
            nombreUsuario=f["nombre_usuario"], idioma=f["idioma"], texto=f["texto"],
            estadoModeracion=f["estado_moderacion"],
        ) for f in pagina],
        siguienteCursor=str(pagina[-1]["comentario_id"]) if len(filas) > limit else None,
    )
