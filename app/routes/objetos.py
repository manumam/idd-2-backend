from typing import Annotated
from fastapi import APIRouter, Path
from app.schemas.errors import RESPUESTAS_FICHA
from app.schemas.objetos import PartidoObjeto
from app.schemas.params import Limit, Skip
from app.services import objetos_service

router = APIRouter(tags=["Objetos IRIS"], responses=RESPUESTAS_FICHA)


@router.get("/objetos/partidos/{id}", response_model=PartidoObjeto,
            summary="Partido y eventos persistentes de la demostración IRIS",
            description="Identidad persistente IRIS, no código de negocio. Eventos paginados por ID. "
                        "Vista del Hito 9, sin sincronización con los partidos operativos de Neo4j.")
def obtener_partido(id: Annotated[int, Path(ge=1, le=2147483647, examples=[1])],
                    limit: Limit = 20, skip: Skip = 0) -> PartidoObjeto:
    return objetos_service.obtener_partido(id, limit, skip)
