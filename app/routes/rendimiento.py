from fastapi import APIRouter

from app.schemas.errors import RESPUESTAS_FICHA
from app.schemas.params import CodigoJugador, CodigoPartido
from app.schemas.rendimiento import AcumuladosJugadorResponse, RendimientoResponse
from app.services.rendimiento_service import obtener_acumulados, obtener_rendimiento

router = APIRouter(tags=['Rendimiento individual'], responses=RESPUESTAS_FICHA)


@router.get('/partidos/{codigo}/jugadores/{jugador_codigo}/estadisticas', response_model=RendimientoResponse,
    summary='Rendimiento de un jugador en un partido',
    description='Goles, asistencias y tarjetas desde eventos MongoDB; distancia en metros y velocidad máxima en km/h desde tracking Influx a 1 Hz confirmado. Redis opcional (5 s). Finales desde resúmenes MongoDB vigentes, sin leer Influx; cierre incompleto devuelve métricas físicas null y estado pendiente. Un jugador no registrado en el encuentro devuelve 404. No incluye autogoles ni tandas como goles individuales.')
def rendimiento(codigo: CodigoPartido, jugador_codigo: CodigoJugador):
    return obtener_rendimiento(codigo, jugador_codigo)


@router.get('/jugadores/{codigo}/estadisticas', response_model=AcumuladosJugadorResponse,
    summary='Acumulados de un jugador en el Mundial 2030',
    description='Agrega una sola vez cada partido: resumen final vigente o eventos del encuentro no consolidado. Solo MongoDB y caché Redis opcional; nunca lee Influx. Suma goles, asistencias, tarjetas y distancias; toma el máximo de velocidades. Cada métrica con cobertura incompleta devuelve null, sin ocultar los valores conocidos por partido. No incluye encuentros próximos, autogoles ni tandas en los goles individuales.')
def acumulados(codigo: CodigoJugador):
    return obtener_acumulados(codigo)
