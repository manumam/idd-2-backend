"""POST/GET /demo/simulacion con un lanzador falso: no se crean procesos."""
import json
from unittest.mock import Mock

import pytest

from app.adapters import mongo_adapter
from app.services import simulacion_demo_service
from app.services.simulacion_demo_service import SimulacionDemo, motivo_no_simulable

TITULARES = [dict(codigo=f"ARG-{d}", nombre=f"Jugador {d}", dorsal=d, posicion="Delantero") for d in range(1, 12)]
ALINEACION_ARG = dict(equipo=dict(codigo="ARG", nombre="Argentina"), titulares=TITULARES, suplentes=[])
ALINEACION_URU = dict(equipo=dict(codigo="URU", nombre="Uruguay"), titulares=[
    {**jugador, "codigo": jugador["codigo"].replace("ARG", "URU")} for jugador in TITULARES
], suplentes=[])
CAMPOS = {"en_curso", "partido", "factor", "segundo_de_juego", "iniciada_en", "finalizada", "error", "siguiente"}


def _partido(**cambios):
    return {**dict(_id="P-002", estado="proximo", eventos=[], resultado=None,
                   local=dict(codigo="ARG", nombre="Argentina"), visitante=dict(codigo="URU", nombre="Uruguay"),
                   fecha_hora="2030-06-09T18:00:00Z",
                   alineaciones=dict(local=ALINEACION_ARG, visitante=ALINEACION_URU)), **cambios}


class ProcesoFalso:
    def __init__(self):
        self.codigo = None
        self.salida = []
        self.error = None
        self.detenido = False

    def codigo_salida(self):
        return self.codigo

    def lineas_salida(self):
        return self.salida

    def ultima_linea_error(self):
        return self.error

    def detener(self):
        self.detenido = True
        self.codigo = 130


class LanzadorFalso:
    def __init__(self):
        self.lanzados = []

    def iniciar(self, partido, factor, directorio):
        proceso = ProcesoFalso()
        self.lanzados.append((partido, factor, proceso))
        return proceso


@pytest.fixture
def lanzador(monkeypatch):
    lanzador = LanzadorFalso()
    monkeypatch.setattr(simulacion_demo_service, "simulacion_demo", SimulacionDemo(lanzador))
    monkeypatch.setattr(mongo_adapter, "find_estadisticas", Mock(return_value=_partido()))
    monkeypatch.setattr(mongo_adapter, "list_candidatos_simulacion", Mock(return_value=[_partido()]))
    return lanzador


def _iniciar(client, **cuerpo):
    return client.post("/demo/simulacion", json={"partido": "P-002", **cuerpo})


def test_estado_inicial(client, lanzador):
    respuesta = client.get("/demo/simulacion")
    assert respuesta.status_code == 200
    assert respuesta.json() == dict(en_curso=False, partido=None, factor=None, segundo_de_juego=None,
                                    iniciada_en=None, finalizada=False, error=None, siguiente="P-002")


def test_lanza_y_responde_202_sin_esperar(client, lanzador):
    respuesta = _iniciar(client)
    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    assert set(cuerpo) == CAMPOS
    assert cuerpo["en_curso"] and cuerpo["partido"] == "P-002" and cuerpo["factor"] == 10
    assert cuerpo["iniciada_en"].endswith("Z") and not cuerpo["finalizada"]
    assert lanzador.lanzados[0][:2] == ("P-002", 10)


def test_sin_partido_elije_el_proximo_simulable(client, lanzador, monkeypatch):
    siguiente = _partido(_id="P-004", fecha_hora="2030-06-10T18:00:00Z")
    monkeypatch.setattr(mongo_adapter, "list_candidatos_simulacion", Mock(return_value=[_partido(estado="finalizado"), siguiente]))
    monkeypatch.setattr(mongo_adapter, "find_estadisticas", Mock(return_value=siguiente))
    respuesta = client.post("/demo/simulacion", json={"factor": 10})
    assert respuesta.status_code == 202
    assert respuesta.json()["partido"] == "P-004"
    assert lanzador.lanzados[0][:2] == ("P-004", 10)


def test_sin_partidos_simulables_responde_409(client, lanzador, monkeypatch):
    monkeypatch.setattr(mongo_adapter, "list_candidatos_simulacion", Mock(return_value=[]))
    respuesta = client.post("/demo/simulacion")
    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "SIN_PARTIDOS_SIMULABLES"


def test_partido_inexistente_404(client, lanzador, monkeypatch):
    monkeypatch.setattr(mongo_adapter, "find_estadisticas", Mock(return_value=None))
    assert _iniciar(client).json()["code"] == "PARTIDO_NO_ENCONTRADO"


@pytest.mark.parametrize("partido", [
    _partido(estado="finalizado"),
    _partido(inicio_tracking="2026-11-20T18:30:00Z"),
    _partido(estadisticas_control=dict(tick=-1)),
    _partido(visitante=None),
    _partido(alineaciones=None),
    _partido(alineaciones=dict(local=None, visitante=ALINEACION_ARG)),
])
def test_partido_no_simulable_409(client, lanzador, monkeypatch, partido):
    monkeypatch.setattr(mongo_adapter, "find_estadisticas", Mock(return_value=partido))
    respuesta = _iniciar(client)
    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "PARTIDO_NO_SIMULABLE"
    assert lanzador.lanzados == []


def test_factor_fuera_de_rango_400(client, lanzador):
    assert _iniciar(client, factor=0).status_code == 400
    assert _iniciar(client, factor=121).status_code == 400
    assert lanzador.lanzados == []


def test_segundo_lanzamiento_en_curso_409(client, lanzador):
    assert _iniciar(client).status_code == 202
    respuesta = _iniciar(client)
    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "SIMULACION_EN_CURSO"
    assert len(lanzador.lanzados) == 1


def test_transicion_a_finalizada(client, lanzador):
    _iniciar(client, factor=20)
    proceso = lanzador.lanzados[0][2]
    proceso.salida = [json.dumps(dict(partido="P-002", tick=4, minuto=45, segundo_de_juego=2700, finalizado=False)),
                      "{", '  "partido": "P-002",']
    assert client.get("/demo/simulacion").json()["segundo_de_juego"] == 2700
    proceso.codigo = 0
    estado = client.get("/demo/simulacion").json()
    assert estado["finalizada"] and not estado["en_curso"] and estado["error"] is None
    assert estado["factor"] == 20
    assert _iniciar(client).status_code == 202


def test_transicion_a_error_con_codigo_de_salida(client, lanzador):
    _iniciar(client)
    proceso = lanzador.lanzados[0][2]
    proceso.codigo, proceso.error = 1, "Simulación interrumpida: ValueError."
    estado = client.get("/demo/simulacion").json()
    assert not estado["en_curso"] and not estado["finalizada"]
    assert estado["error"] == "El simulador terminó con código 1: Simulación interrumpida: ValueError."


def test_cierre_de_la_api_detiene_el_proceso(lanzador):
    simulacion = simulacion_demo_service.simulacion_demo
    simulacion.iniciar("P-002", 10)
    simulacion_demo_service.detener_simulacion()
    assert lanzador.lanzados[0][2].detenido


def test_condiciones_compartidas_con_el_simulador():
    assert motivo_no_simulable(_partido()) is None
    assert "restaurarlo" in motivo_no_simulable(_partido(inicio_tracking="x"))
    assert "próximo" in motivo_no_simulable(_partido(estado="en_vivo"))
