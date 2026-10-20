import random

import pytest

from chargegrid.solar import gerar_fatores_nuvem, potencia_solar_kw


def test_zero_antes_do_nascer_e_depois_do_poente():
    for minuto in (0, 5 * 60 + 55, 6 * 60, 18 * 60, 23 * 60):
        assert potencia_solar_kw(minuto) == 0.0


def test_pico_ao_meio_dia_e_kwp_vezes_derate():
    assert potencia_solar_kw(12 * 60) == pytest.approx(15.0 * 0.85)


def test_curva_simetrica_em_torno_do_meio_dia():
    assert potencia_solar_kw(9 * 60) == pytest.approx(potencia_solar_kw(15 * 60))


def test_nuvem_reduz_proporcionalmente():
    assert potencia_solar_kw(12 * 60, 0.5) == pytest.approx(potencia_solar_kw(12 * 60) * 0.5)


def test_fatores_de_nuvem_tem_um_valor_por_tick_na_faixa_e_sao_deterministicos():
    a = gerar_fatores_nuvem(random.Random(7))
    b = gerar_fatores_nuvem(random.Random(7))
    assert a == b
    assert len(a) == 288
    assert all(0.35 <= f <= 1.0 for f in a)


def test_alguma_seed_produz_nuvem():
    assert any(min(gerar_fatores_nuvem(random.Random(s))) < 1.0 for s in range(20))


def test_potencia_escala_com_o_tamanho_da_usina():
    assert potencia_solar_kw(12 * 60, 1.0, 30.0) == pytest.approx(2 * potencia_solar_kw(12 * 60))
    assert potencia_solar_kw(12 * 60, 1.0, 0.0) == 0.0
