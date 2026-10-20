from decimal import Decimal

import pytest

from chargegrid.tarifacao import (
    custo_do_intervalo,
    custo_rede_do_intervalo,
    custo_rede_kwh,
    eh_pico,
    em_reais,
    posto_tarifario,
    tarifa_no_instante,
)


def test_fronteiras_da_faixa_de_pico():
    assert not eh_pico(17 * 60 + 55)
    assert eh_pico(18 * 60)
    assert eh_pico(20 * 60 + 55)
    assert not eh_pico(21 * 60)


def test_tarifa_por_instante():
    assert tarifa_no_instante(10 * 60) == Decimal("0.85")
    assert tarifa_no_instante(19 * 60) == Decimal("1.40")


def test_custo_do_intervalo_usa_a_tarifa_da_faixa():
    assert custo_do_intervalo(1.0, 19 * 60) == Decimal("1.4000")
    assert custo_do_intervalo(2.0, 10 * 60) == Decimal("1.7000")
    assert custo_do_intervalo(0.0, 19 * 60) == Decimal("0.0000")


def test_energia_negativa_e_rejeitada():
    with pytest.raises(ValueError):
        custo_do_intervalo(-0.1, 600)


def test_sessao_que_atravessa_o_pico_e_cobrada_por_intervalo():
    # 17:55 (normal) + 18:00 (pico), 1 kWh cada
    total = custo_do_intervalo(1.0, 17 * 60 + 55) + custo_do_intervalo(1.0, 18 * 60)
    assert total == Decimal("2.2500")


def test_em_reais_arredonda_meio_para_cima():
    assert em_reais(Decimal("1.005")) == Decimal("1.01")
    assert em_reais(Decimal("2.2500")) == Decimal("2.25")


@pytest.mark.parametrize(
    ("minuto", "posto"),
    [
        (16 * 60 + 25, "fora_ponta"),
        (16 * 60 + 30, "intermediario"),
        (17 * 60 + 25, "intermediario"),
        (17 * 60 + 30, "ponta"),
        (20 * 60 + 25, "ponta"),
        (20 * 60 + 30, "intermediario"),
        (21 * 60 + 25, "intermediario"),
        (21 * 60 + 30, "fora_ponta"),
        (3 * 60, "fora_ponta"),
    ],
)
def test_postos_da_tarifa_branca_nas_fronteiras(minuto, posto):
    assert posto_tarifario(minuto) == posto


def test_custo_da_rede_segue_a_tarifa_branca_e_a_ponta_custa_mais_que_o_preco_ao_cliente():
    assert custo_rede_kwh(18 * 60) == Decimal("1.55911")
    assert custo_rede_kwh(17 * 60) == Decimal("1.03179")
    assert custo_rede_kwh(12 * 60) == Decimal("0.68501")
    assert custo_rede_kwh(18 * 60) > tarifa_no_instante(18 * 60)  # o sinal que a Sprint 4 usa
    assert custo_rede_do_intervalo(2.0, 18 * 60) == Decimal("3.1182")
    with pytest.raises(ValueError):
        custo_rede_do_intervalo(-1.0, 600)
