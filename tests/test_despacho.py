import math
import random

import pytest

from chargegrid import config as cfg
from chargegrid.bateria import Bateria
from chargegrid.despacho import (
    despachar,
    plano_da_bateria,
    reserva_para_pico_kwh,
    sobra_solar_prevista_kwh,
)

H = 5 / 60


def _bat(soc=0.5):
    return Bateria(20.0, 10.0, 0.9, 0.1, soc=soc)


def _fecha(d):
    assert d.solar_para_carga_kw + d.bateria_para_carga_kw + d.rede_kw == pytest.approx(d.carga_kw)
    assert d.solar_para_carga_kw + d.solar_para_bateria_kw + d.excedente_kw == pytest.approx(
        d.solar_kw
    )


def test_sem_bateria_solar_primeiro_e_o_resto_da_rede():
    d = despachar(10.0, 4.0, None, 24.0, H)
    _fecha(d)
    assert (d.solar_para_carga_kw, d.rede_kw, d.excedente_kw) == (4.0, 6.0, 0.0)


def test_autoconsumo_sobra_de_sol_carrega_e_deficit_descarrega():
    b = _bat()
    d = despachar(3.0, 8.0, b, 24.0, H)
    _fecha(d)
    assert d.solar_para_bateria_kw == pytest.approx(5.0) and d.rede_kw == 0.0
    d2 = despachar(12.0, 0.0, b, 24.0, H)
    _fecha(d2)
    assert d2.bateria_para_carga_kw == pytest.approx(10.0) and d2.rede_kw == pytest.approx(2.0)


def test_guardar_solar_manda_sol_para_a_bateria_e_carros_para_a_rede():
    d = despachar(8.0, 6.0, _bat(), 24.0, H, guardar_kw=4.0, descarga_livre_kw=0.0)
    _fecha(d)
    assert d.solar_para_bateria_kw == pytest.approx(4.0)
    assert d.solar_para_carga_kw == pytest.approx(2.0) and d.rede_kw == pytest.approx(6.0)


def test_guardar_solar_nunca_empurra_a_rede_acima_do_limite():
    d = despachar(28.0, 6.0, _bat(), 24.0, H, guardar_kw=6.0, descarga_livre_kw=0.0)
    _fecha(d)
    assert d.rede_kw <= 24.0 + 1e-9
    assert d.solar_para_bateria_kw == pytest.approx(2.0)


def test_corte_de_pico_descarrega_so_o_excesso_quando_a_descarga_livre_e_zero():
    d = despachar(30.0, 0.0, _bat(), 24.0, H, descarga_livre_kw=0.0)
    _fecha(d)
    assert d.bateria_para_carga_kw == pytest.approx(6.0) and d.rede_kw == pytest.approx(24.0)


def test_bateria_nunca_carrega_pela_rede():
    b = _bat(0.2)
    d = despachar(0.0, 0.0, b, 24.0, H, guardar_kw=10.0)
    assert d.solar_para_bateria_kw == 0.0 and d.rede_kw == 0.0
    assert b.soc == pytest.approx(0.2)


def test_propriedade_balanco_e_limite_em_despachos_aleatorios():
    rng = random.Random(4)
    for _ in range(500):
        b = _bat(rng.uniform(0.1, 1.0))
        solar = rng.uniform(0, 13)
        teto = 24.0 + solar + b.max_descarga_kw(H)
        carga = rng.uniform(0, teto)
        antes = b.energia_kwh
        d = despachar(
            carga,
            solar,
            b,
            24.0,
            H,
            guardar_kw=rng.choice([0.0, rng.uniform(0, 10)]),
            descarga_livre_kw=rng.choice([0.0, math.inf, rng.uniform(0, 10)]),
        )
        _fecha(d)
        assert d.rede_kw <= 24.0 + 1e-6
        assert not (d.solar_para_bateria_kw > 0 and d.bateria_para_carga_kw > 0)
        esperado = antes + (d.solar_para_bateria_kw * 0.9 - d.bateria_para_carga_kw) * H
        assert b.energia_kwh == pytest.approx(esperado, abs=1e-9)
        assert 0.1 - 1e-9 <= b.soc <= 1.0 + 1e-9


DEMANDA_BAIXA = [0.0] * 24
DEMANDA_ALTA_DE_DIA = [0.0] * 6 + [20.0] * 12 + [0.0] * 6


def test_sobra_prevista_e_maior_quando_a_demanda_prevista_e_menor():
    baixa = sobra_solar_prevista_kwh(DEMANDA_BAIXA, 8 * 60, 15.0, 0.9)
    alta = sobra_solar_prevista_kwh(DEMANDA_ALTA_DE_DIA, 8 * 60, 15.0, 0.9)
    assert baixa > 40 and alta == 0.0
    assert sobra_solar_prevista_kwh(DEMANDA_BAIXA, cfg.PONTA_MIN[0], 15.0, 0.9) == 0.0


def test_plano_guarda_sol_so_quando_a_sobra_prevista_nao_enche_a_bateria():
    guardar, livre, _ = plano_da_bateria(_bat(0.1), 8 * 60, DEMANDA_BAIXA, 24.0, 15.0, H)
    assert guardar == 0.0 and livre > 0  # vai sobrar sol: pode até usar a bateria agora
    guardar, livre, _ = plano_da_bateria(_bat(0.1), 8 * 60, DEMANDA_ALTA_DE_DIA, 24.0, 15.0, H)
    assert guardar > 0 and livre == 0.0  # não vai sobrar sol: guarda agora


def test_plano_na_ponta_libera_a_energia_acima_da_reserva():
    demanda = [0.0] * 20 + [30.0, 30.0, 0.0, 0.0]  # 6 kW acima do limite às 20h e 21h
    guardar, livre, reserva = plano_da_bateria(_bat(1.0), 18 * 60, demanda, 24.0, 15.0, H)
    assert guardar == 0.0
    assert reserva == pytest.approx(12.0)
    assert livre == pytest.approx((18.0 - 12.0) / H)


def test_reserva_conta_so_o_resto_da_hora_corrente():
    demanda = [0.0] * 20 + [30.0] + [0.0] * 3
    assert reserva_para_pico_kwh(demanda, 20 * 60 + 30, 24.0, 15.0) == pytest.approx(3.0)
    assert reserva_para_pico_kwh(demanda, 21 * 60, 24.0, 15.0) == 0.0
