"""Simulación en vivo con reloj y adaptadores en memoria: no duerme ni escribe bases."""
import pytest

from app.services.seguimiento_service import TickPartido
from scripts.simular_en_vivo import RelojSimulado, ticks_vencidos


def _ticks(*minutos):
    return [TickPartido(reloj=dict(periodo='primer_tiempo', minuto=m)) for m in minutos]


def test_reloj_factor_diez_juega_noventa_minutos_en_nueve():
    reloj = RelojSimulado()
    assert reloj.segundo_en(0) == 0
    assert reloj.segundo_en(0.09) == 0
    assert reloj.segundo_en(1.25) == 12
    assert reloj.segundo_en(540) == 5400
    assert reloj.segundo_en(10_000) == 5400
    assert reloj.transcurrido_para(5400) == 540


def test_reloj_otro_factor_y_valores_invalidos():
    assert RelojSimulado(factor=1).segundo_en(61.9) == 61
    assert RelojSimulado(factor=0.5).transcurrido_para(30) == 60
    for factor in (0, -1, float('inf'), float('nan')):
        with pytest.raises(ValueError):
            RelojSimulado(factor)
    with pytest.raises(ValueError):
        RelojSimulado().segundo_en(-0.1)


def test_pendientes_no_repite_ni_saltea_segundos():
    reloj = RelojSimulado()
    assert list(reloj.pendientes(-1, 0)) == [0]
    assert list(reloj.pendientes(0, 0.35)) == [1, 2, 3]
    assert list(reloj.pendientes(3, 0.35)) == []
    assert list(reloj.pendientes(5398, 9999)) == [5399, 5400]


def test_ticks_del_guion_vencen_en_su_minuto():
    ticks = _ticks(0, 12, 28, 45, 46, 90)
    assert ticks_vencidos(ticks, 0, 0) == [0]
    assert ticks_vencidos(ticks, 1, 719) == []
    assert ticks_vencidos(ticks, 1, 720) == [1]
    # Un salto real largo dispara todos los ticks alcanzados, en orden.
    assert ticks_vencidos(ticks, 2, 2760) == [2, 3, 4]
    assert ticks_vencidos(ticks, 5, 5400) == [5]
    assert ticks_vencidos(ticks, 6, 5400) == []
