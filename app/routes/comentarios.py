from typing import Annotated
from fastapi import APIRouter, Path, Query

from app.schemas.comentarios import ComentariosPagina
from app.schemas.errors import RESPUESTAS_LISTA
from app.schemas.params import FechaHora, Limit
from app.services.comentarios_service import listar_comentarios

router = APIRouter(tags=["Comentarios"], responses=RESPUESTAS_LISTA)
PartidoComentarios = Annotated[str, Path(
    pattern=r"^[A-Z]{3}-[A-Z]{3}-[0-9]{8}$", examples=["ARG-ESP-20300624"],
    description="Identificador nativo del Hito 6; no es el código de Neo4j.",
)]


@router.get("/partidos/{codigo}/comentarios", response_model=ComentariosPagina,
            summary="Feed de una ventana de cinco minutos",
            description="Partición exacta de Cassandra. Más nuevos primero; cursor timeuuid exclusivo. "
                        "Sin datos devuelve 200 vacío. El feed vence a los 14 días.")
def comentarios(codigo: PartidoComentarios, bloque: FechaHora, limit: Limit = 20,
                cursor: Annotated[str | None, Query(max_length=36)] = None) -> ComentariosPagina:
    return listar_comentarios(codigo, bloque, limit, cursor)
