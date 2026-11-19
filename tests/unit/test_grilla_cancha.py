import pytest

from app.services.grilla_cancha import (
    COLUMNAS, FILAS, Celda, celda_desde_id, celdas_con_intensidad, id_celda, parametros_grilla,
)


def test_dimensiones_de_la_grilla():
    assert (COLUMNAS, FILAS) == (21, 14)


def test_parametros_que_recibe_la_consulta():
    assert parametros_grilla() == {
        "largo_m": 105.0, "ancho_m": 68.0, "lado_m": 5.0, "ultima_columna": 20, "ultima_fila": 13,
    }


def test_id_celda_y_parseo():
    assert id_celda(Celda(7, 2)) == "7_2"
    assert celda_desde_id("7_2") == Celda(7, 2)
    assert celda_desde_id(id_celda(Celda(20, 13))) == Celda(20, 13)


@pytest.mark.parametrize("valor", ["", "7", "7_2_1", "a_2", "-1_2", "21_0", "0_14"])
def test_id_celda_invalido(valor):
    assert celda_desde_id(valor) is None


def test_intensidad_normalizada_al_maximo():
    celdas = celdas_con_intensidad({Celda(3, 1): 30, Celda(0, 0): 60, Celda(5, 5): 0})
    assert celdas == [
        {"columna": 0, "fila": 0, "muestras": 60, "intensidad": 1.0},
        {"columna": 3, "fila": 1, "muestras": 30, "intensidad": 0.5},
    ]


def test_sin_muestras_no_hay_celdas():
    assert celdas_con_intensidad({}) == []
    assert celdas_con_intensidad({Celda(0, 0): 0}) == []
