from typing import Annotated
from fastapi import APIRouter, Path
from app.schemas.errors import RESPUESTAS_FICHA, RESPUESTAS_LISTA
from app.schemas.grupos import GruposResponse, PosicionesResponse
from app.services.grupos_service import listar_grupos, consultar_posiciones

router = APIRouter(tags=['Grupos'])


@router.get('/grupos', response_model=GruposResponse, responses=RESPUESTAS_LISTA,
            summary='Consultar los grupos', description='Participantes y reglas de la demo desde MongoDB. Sin datos: items vacío.')
def obtener_grupos() -> GruposResponse:
    return listar_grupos()


@router.get('/grupos/{id}/posiciones', response_model=PosicionesResponse, responses=RESPUESTAS_FICHA,
            summary='Consultar posiciones y partidos de un grupo',
            description='Solo cuentan resultados finalizados, sin goles de tanda. Orden: puntos, diferencia de gol, goles a favor y orden del dataset. Redis opcional, versionado por reglas y partidos para reflejar cierres y correcciones. completa indica que terminaron todos los cruces esperados.')
def obtener_posiciones(id: Annotated[str, Path(pattern=r'^[A-P]$')]) -> PosicionesResponse:
    return consultar_posiciones(id)
