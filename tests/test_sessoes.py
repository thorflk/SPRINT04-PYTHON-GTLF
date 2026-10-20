import random
from decimal import Decimal

import pytest

from chargegrid import config as cfg
from chargegrid.sessoes import (
    Chegada,
    Sessao,
    criar_sessao,
    gerar_chegadas,
    potencia_desejada_kw,
    soc_alcancavel,
)
from chargegrid.veiculos import Veiculo

CARRO = Veiculo("Teste", 11.0, 50.0)


def _sessao(soc_inicial=0.5, alvo=0.8, tick_saida=48):
    return Sessao(1, "P2", CARRO, soc_inicial, alvo, tick_inicio=0, tick_saida=tick_saida)


def test_plato_e_o_menor_entre_nominal_e_obc():
    assert potencia_desejada_kw(22.0, CARRO, 0.3) == 11.0
    assert potencia_desejada_kw(7.4, CARRO, 0.3) == 7.4


def test_taper_comeca_em_80_por_cento_sem_salto():
    assert potencia_desejada_kw(11.0, CARRO, 0.80) == pytest.approx(11.0)


def test_taper_termina_em_10_por_cento_do_nominal():
    assert potencia_desejada_kw(11.0, CARRO, 1.0) == pytest.approx(1.1)


def test_potencia_nunca_cresce_com_o_soc():
    valores = [potencia_desejada_kw(11.0, CARRO, s / 100) for s in range(10, 101)]
    assert all(a >= b - 1e-12 for a, b in zip(valores, valores[1:]))


def test_avancar_entrega_energia_igual_ao_delta_de_soc_da_bateria():
    s = _sessao(0.5, 0.8)  # 0,3 x 50 kWh = 15 kWh
    for _ in range(100):
        if s.atingiu_alvo:
            break
        s.avancar(11.0)
    assert s.atingiu_alvo
    assert s.energia_kwh == pytest.approx(15.0, abs=1e-9)
    assert s.soc == pytest.approx(0.8)


def test_avancar_nunca_passa_do_alvo_num_unico_tick():
    s = _sessao(0.79, 0.80)  # faltam 0,5 kWh; 11 kW x 5 min = 0,917 kWh
    assert s.avancar(11.0) == pytest.approx(0.5)
    assert s.atingiu_alvo


def test_avancar_com_potencia_zero_nao_entrega_energia():
    s = _sessao()
    assert s.avancar(0.0) == 0.0
    assert s.soc == 0.5


def test_avancar_rejeita_potencia_negativa():
    with pytest.raises(ValueError):
        _sessao().avancar(-1.0)


def test_registrar_acumula_renovavel_custo_pico_e_corte():
    s = _sessao()
    s.registrar(2.0, 0.25, Decimal("2.8000"), em_pico=True, em_corte=True)
    s.registrar(1.0, 0.0, Decimal("0.8500"), em_pico=False, em_corte=False)
    assert s.energia_renovavel_kwh == pytest.approx(0.5)
    assert s.energia_pico_kwh == pytest.approx(2.0)
    assert s.custo == Decimal("3.6500")
    assert s.custo_pico == Decimal("2.8000")
    assert s.ticks_em_corte == 1


def _chegada(soc=0.2, alvo=1.0, permanencia_ticks=24):
    return Chegada(10, CARRO, soc, alvo, 10 + permanencia_ticks, ("P2", "P1", "P3", "P4"))


def test_promessa_e_o_alvo_quando_ha_tempo_de_sobra():
    s = criar_sessao(1, "P2", _chegada(soc=0.5, alvo=0.8, permanencia_ticks=60))
    assert s.alvo == pytest.approx(0.8)
    assert s.tick_saida == 70 and s.alvo_pedido == 0.8


def test_promessa_fica_abaixo_do_alcancavel_na_potencia_maxima():
    s = criar_sessao(1, "P2", _chegada(soc=0.2, alvo=1.0, permanencia_ticks=12))  # 1 h
    maximo = soc_alcancavel(11.0, CARRO, 0.2, 12)
    assert s.alvo < maximo
    assert s.alvo == pytest.approx(
        soc_alcancavel(11.0, CARRO, 0.2, 12, cfg.FATOR_PROMESSA), abs=1e-4
    )


def test_promessa_e_cumprivel_carregando_sozinho_a_potencia_maxima():
    s = criar_sessao(1, "P3", _chegada(soc=0.1, alvo=1.0, permanencia_ticks=30))
    for _ in range(s.tick_inicio, s.tick_saida):
        s.avancar(s.potencia_desejada_kw(cfg.PONTOS["P3"]))
    assert s.atingiu_alvo


def test_potencia_desejada_e_zero_depois_de_atingir_a_promessa():
    s = _sessao(0.79, 0.80)
    s.avancar(11.0)
    assert s.potencia_desejada_kw(11.0) == 0.0


def test_folga_diminui_com_o_tempo_e_piso_cresce_perto_da_saida():
    s = _sessao(0.5, 0.8, tick_saida=30)  # faltam 15 kWh; 11 kW => 1,36 h; 2,5 h disponíveis
    assert s.folga_h(0, 11.0) == pytest.approx(2.5 - 15 / 11)
    assert s.folga_h(10, 11.0) < s.folga_h(0, 11.0)
    assert s.piso_kw(0, 11.0, 0.6) == 0.0  # dá para adiar
    assert s.piso_kw(25, 11.0, 0.6) == pytest.approx(11.0)  # não dá mais


def test_piso_garante_a_promessa_mesmo_adiando_ao_maximo():
    s = _sessao(0.3, 0.8, tick_saida=40)
    for tick in range(0, 40):
        s.avancar(s.piso_kw(tick, 11.0, 0.6))
    assert s.atingiu_alvo


def test_chegadas_sao_deterministicas_ordenadas_e_saem_ate_meia_noite():
    a = gerar_chegadas(random.Random(3))
    assert a == gerar_chegadas(random.Random(3))
    assert 4 <= len(a) <= 12
    assert [c.tick for c in a] == sorted(c.tick for c in a)
    for c in a:
        assert c.tick < c.tick_saida <= cfg.TICKS_POR_DIA
        assert sorted(c.preferencia) == sorted(cfg.PONTOS)
        assert cfg.SOC_INICIAL_MIN <= c.soc_inicial <= cfg.SOC_INICIAL_MAX
        assert c.alvo_pedido in cfg.ALVOS_SOC


def test_permanencia_respeita_a_faixa_quando_nao_bate_na_meia_noite():
    for seed in range(30):
        for c in gerar_chegadas(random.Random(seed)):
            if c.tick_saida < cfg.TICKS_POR_DIA:
                horas = (c.tick_saida - c.tick) * cfg.PASSO_MIN / 60
                assert cfg.PERMANENCIA_H[0] - 0.05 <= horas <= cfg.PERMANENCIA_H[1] + 0.05


def test_chegadas_concentram_no_fim_da_tarde_e_noite():
    noite = total = 0
    for seed in range(100):
        for c in gerar_chegadas(random.Random(seed)):
            total += 1
            if 18 <= (c.tick * cfg.PASSO_MIN) // 60 < 22:
                noite += 1
    assert noite / total > 0.5
