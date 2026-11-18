from fastapi import APIRouter
from app.schemas.errors import RESPUESTAS_LISTA
from app.schemas.playoffs import PlayoffsResponse
from app.services.playoffs_service import consultar_playoffs

router = APIRouter(tags=['Playoffs'])


@router.get('/playoffs', response_model=PlayoffsResponse, responses=RESPUESTAS_LISTA,
            summary='Consultar el cuadro de eliminatorias',
            description='Cruces ordenados por ronda y orden visual desde MongoDB. Plazas por equipo, puesto de grupo completo o ganador anterior. Incluye partido, origen, ganador y siguiente cruce. Redis opcional versionado por todas las entradas: cierres y correcciones recalculan sin escrituras. Un resultado con participantes obsoletos o sin desempate válido requiere_revision y no propaga ganador. Sin cuadro cargado devuelve items vacío. Reglas explícitas de la demo: dos clasificados por grupo, sin mejores terceros.')
def obtener_playoffs() -> PlayoffsResponse:
    return consultar_playoffs()
