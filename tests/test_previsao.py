from dataclasses import replace

import pandas as pd
import pytest

from chargegrid import config as cfg
from chargegrid.previsao import ajustar, backtest, gerar_historico, recomendacoes
from chargegrid.simulacao import simular_dia


@pytest.fixture(scope="module")
def historico():
    return gerar_historico(8)


@pytest.fixture(scope="module")
def prev(historico):
    return ajustar(historico)


def test_historico_gera_um_dia_por_seed_distinta(historico):
    assert len(historico) == 8
    assert not historico[0].equals(historico[1])


def test_por_hora_tem_24_linhas_e_colunas_esperadas(prev):
    assert list(prev.por_hora["hora"]) == list(range(24))
    assert {"media_kw", "desvio_kw", "solar_medio_kw"} <= set(prev.por_hora.columns)
    assert not prev.por_hora.isna().any().any()


def test_pico_previsto_cai_na_faixa_noturna_do_perfil_shopping(prev):
    inicio, fim, media = prev.janela_pico
    assert fim - inicio == cfg.LARGURA_JANELA_PICO_H
    assert 16 <= inicio <= 21
    assert media > 0


def test_melhores_horas_tem_sol_e_ficam_fora_do_pico_tarifario(prev):
    assert 1 <= len(prev.melhores_horas) <= cfg.TOP_HORAS_RECOMENDADAS
    solar = prev.por_hora.set_index("hora")["solar_medio_kw"]
    for hora in prev.melhores_horas:
        assert solar[hora] >= cfg.SOLAR_MINIMO_RECOMENDACAO_KW
        assert not (cfg.HORA_PICO_INICIO <= hora < cfg.HORA_PICO_FIM)
    assert prev.melhores_horas == sorted(prev.melhores_horas)


def test_modelo_horario_supera_baseline_constante_em_dias_nao_vistos(prev):
    erros_modelo, erros_base = [], []
    for seed in (cfg.SEED_DEMO, 5, 7, 9):
        bt = backtest(prev, simular_dia(seed).telemetria)
        erros_modelo.append(bt["mae_kw"])
        erros_base.append(bt["mae_baseline_kw"])
    assert sum(erros_modelo) < sum(erros_base)


def test_backtest_devolve_erros_nao_negativos(prev):
    bt = backtest(prev, simular_dia(cfg.SEED_DEMO).telemetria)
    assert bt["mae_kw"] >= 0 and bt["mae_baseline_kw"] >= 0


def test_recomendacoes_mencionam_pico_horarios_e_economia(prev):
    textos = recomendacoes(prev, cfg.LIMITE_OPERACIONAL_KW)
    junto = " ".join(textos)
    assert "Pico previsto" in junto
    assert "Melhores horários" in junto
    assert "16,50" in junto  # 30 kWh x (1,40 - 0,85)
    assert all(isinstance(t, str) for t in textos)


@pytest.mark.parametrize(
    ("janela", "esperado"),
    [
        ((18, 21, 20.0), "cobre toda essa janela"),
        ((19, 22, 20.0), "cobre só parte dessa janela"),
        ((10, 13, 5.0), "não coincide com a faixa"),
    ],
)
def test_recomendacao_descreve_a_sobreposicao_real_com_a_tarifa_de_pico(prev, janela, esperado):
    textos = recomendacoes(replace(prev, janela_pico=janela), cfg.LIMITE_OPERACIONAL_KW)
    assert any(esperado in t for t in textos)


def test_ajustar_aceita_historico_de_um_unico_dia():
    p = ajustar([pd.concat([simular_dia(1).telemetria])])
    assert (p.por_hora["desvio_kw"] == 0).all()
