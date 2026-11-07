from fastapi import APIRouter

from app.schemas.errors import RESPUESTA_503
from app.schemas.fixture import FixtureResponse
from app.services.fixture_service import consultar_fixture

router = APIRouter(tags=["Fixture"], responses=RESPUESTA_503)


@router.get(
    "/fixture", response_model=FixtureResponse, summary="Consultar el fixture",
    description="Mundial 2030 completo, ordenado por fecha y código. Horarios UTC. "
                "Sin partidos devuelve items vacío. Redis es opcional; caché de 5 s por defecto.",
)
def obtener_fixture() -> FixtureResponse:
    return consultar_fixture()
