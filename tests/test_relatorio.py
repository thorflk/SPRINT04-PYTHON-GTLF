import json

import pytest

from chargegrid import config as cfg
from chargegrid.previsao import ajustar, backtest, gerar_historico, recomendacoes
from chargegrid.relatorio import (
    barra,
    formatar_dashboard,
    formatar_linha_ao_vivo,
    ganhos,
    metricas,
    montar_resumo,
    salvar_saidas,
    sessoes_para_df,
    tabela_cenarios,
    tabela_resultados_markdown,
)
from chargegrid.simulacao import simular_cenarios


@pytest.fixture(scope="module")
def contexto():
    resultados = simular_cenarios(cfg.SEED_DEMO)
    prev = ajustar(gerar_historico(6))
    bt = backtest(prev, resultados["D"].telemetria)
    return resultados, prev, bt, montar_resumo(resultados, prev, bt)


def test_metricas_energias_fecham(contexto):
    resultados, *_ = contexto
    for res in resultados.values():
        m = metricas(res)
        soma = m["energia_solar_kwh"] + m["energia_bateria_kwh"] + m["energia_rede_kwh"]
        assert soma == pytest.approx(m["energia_entregue_kwh"], abs=0.03)
        assert m["energia_entregue_kwh"] == pytest.approx(
            sum(s.energia_kwh for s in res.sessoes), abs=0.02
        )
        assert 0 <= m["pct_renovavel"] <= 100
        assert 0 <= m["pct_promessas"] <= 100


def test_metricas_financeiras_e_de_co2_seguem_as_formulas(contexto):
    resultados, *_ = contexto
    m = metricas(resultados["D"])
    assert m["margem_brl"] == pytest.approx(m["receita_brl"] - m["custo_rede_brl"], abs=0.02)
    assert m["co2_rede_kg"] == pytest.approx(
        m["energia_rede_kwh"] * cfg.FATOR_EMISSAO_REDE_KG_KWH, abs=0.01
    )
    esperado = m["energia_entregue_kwh"] / cfg.CONSUMO_VEICULO_KWH_KM * cfg.EMISSAO_KG_CO2_KM
    assert m["co2_evitado_vs_combustao_kg"] == pytest.approx(esperado, abs=0.02)


def test_ganhos_sao_diferencas_entre_cenarios(contexto):
    resultados, *_ = contexto
    comp = tabela_cenarios(resultados)
    g = ganhos(comp, "A", "D")
    a, d = comp.loc["A"], comp.loc["D"]
    assert g["custo_rede_brl"] == pytest.approx(a["custo_rede_brl"] - d["custo_rede_brl"])
    assert g["custo_rede_pct"] == pytest.approx(
        100 * g["custo_rede_brl"] / a["custo_rede_brl"], abs=0.05
    )
    assert g["custo_rede_brl"] > 0 and g["energia_rede_kwh"] > 0


def test_resumo_traz_cenarios_ganhos_e_previsao(contexto):
    _, prev, bt, r = contexto
    assert set(r["cenarios"]) == {"A", "B", "C", "D"}
    assert r["solucao_final"]["cenario"] == "D"
    ini, fim, _ = prev.janela_pico
    assert r["previsao_janela_pico"] == f"{ini}h-{fim}h"
    assert r["previsao_mae_kw"] == bt["mae_kw"]
    assert r["mensagens_ocpp"]["StartTransaction"] == r["solucao_final"]["sessoes"]


def test_sessoes_para_df_vazio_mantem_as_colunas():
    df = sessoes_para_df([])
    assert len(df) == 0
    assert {"id", "ponto", "veiculo", "soc_prometido", "promessa_cumprida"} <= set(df.columns)


def test_sessoes_para_df_tem_uma_linha_por_sessao(contexto):
    resultados, *_ = contexto
    df = sessoes_para_df(resultados["D"].sessoes)
    assert len(df) == len(resultados["D"].sessoes)
    assert (df["permanencia_min"] > 0).all()
    assert (df["soc_final"] <= df["soc_prometido"] + 1e-3).all()


def test_salvar_saidas_grava_os_arquivos(contexto, tmp_path):
    resultados, _, _, r = contexto
    caminhos = salvar_saidas(resultados, r, tmp_path)
    assert {c.name for c in caminhos} == {
        "telemetria.csv",
        "sessoes.csv",
        "cenarios.csv",
        "ocpp_log.jsonl",
        "resumo.json",
    }
    assert all(c.stat().st_size > 0 for c in caminhos)
    assert json.loads((tmp_path / "resumo.json").read_text(encoding="utf-8"))["seed"] == r["seed"]
    primeira = (tmp_path / "ocpp_log.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(primeira)["mensagem"][0] == 2


def test_dashboard_lista_comparacao_bateria_e_recomendacoes(contexto):
    resultados, prev, _, r = contexto
    textos = recomendacoes(prev, cfg.LIMITE_OPERACIONAL_KW)
    texto = formatar_dashboard(
        r, textos, sessoes_para_df(resultados["D"].sessoes), tabela_cenarios(resultados)
    )
    for trecho in (
        "CHARGEGRID",
        "Bateria",
        "4 estratégias",
        "Custo da rede",
        "CO₂",
        "Pico previsto",
    ):
        assert trecho in texto


def test_tabela_markdown_tem_os_quatro_cenarios(contexto):
    resultados, *_ = contexto
    md = tabela_resultados_markdown(tabela_cenarios(resultados))
    assert md.splitlines()[0].count("|") == 6
    assert "Custo da energia da rede" in md and "Sem gestão" in md


def test_barra_limita_entre_zero_e_o_maximo():
    assert barra(0, 10, 10) == "[░░░░░░░░░░]"
    assert barra(5, 10, 10) == "[█████░░░░░]"
    assert barra(99, 10, 10) == "[██████████]"
    assert barra(3, 0, 10) == "[░░░░░░░░░░]"


def test_linha_ao_vivo_mostra_bateria_posto_eventos_e_reducao(contexto):
    resultados, *_ = contexto
    t = resultados["D"].telemetria
    linha = t[t["em_corte"]].iloc[0].to_dict()
    texto = formatar_linha_ao_vivo(linha, ["SetChargingProfile P2 -> 5.3 kW"])
    assert linha["hora"] in texto and "REDUZ" in texto and "bat" in texto
    assert "SetChargingProfile P2" in texto
    ponta = t[t["posto"] == "ponta"].iloc[0].to_dict()
    assert "PONTA" in formatar_linha_ao_vivo(ponta, [])
    sem_bateria = resultados["B"].telemetria.iloc[0].to_dict()
    assert "bat" not in formatar_linha_ao_vivo(sem_bateria, [])
