import pytest

from chargegrid import config as cfg
from chargegrid.estrategias import ESTRATEGIAS, FINAL, PADRAO, SEM_GESTAO
from chargegrid.relatorio import metricas
from chargegrid.simulacao import simular_cenarios, simular_dia

H = cfg.PASSO_MIN / 60


@pytest.fixture(scope="module")
def demo():
    return simular_cenarios(cfg.SEED_DEMO)


def test_uma_linha_de_telemetria_por_tick(demo):
    for res in demo.values():
        assert len(res.telemetria) == cfg.TICKS_POR_DIA
        assert list(res.telemetria["tick"]) == list(range(cfg.TICKS_POR_DIA))


def test_mesma_seed_produz_resultado_identico():
    a, b = simular_dia(7), simular_dia(7)
    assert a.telemetria.equals(b.telemetria)
    assert [m.como_dict() for m in a.ocpp.mensagens] == [m.como_dict() for m in b.ocpp.mensagens]


def test_o_dia_de_demanda_e_o_mesmo_em_todas_as_estrategias(demo):
    chave = lambda r: [  # noqa: E731
        (s.ponto, s.veiculo, s.tick_inicio, s.tick_saida, s.alvo) for s in r.sessoes
    ]
    referencia = chave(demo["A"])
    assert all(chave(r) == referencia for r in demo.values())
    assert len({r.recusadas for r in demo.values()}) == 1


@pytest.mark.parametrize("codigo", list(ESTRATEGIAS))
@pytest.mark.parametrize("seed", range(1, 16))
def test_invariantes_fisicos_em_todos_os_ticks(seed, codigo):
    res = simular_dia(seed, ESTRATEGIAS[codigo])
    t = res.telemetria
    fonte = t["solar_usada_kw"] + t["bateria_kw"] + t["rede_kw"]
    assert (fonte - t["entregue_kw"]).abs().max() < 1e-6
    destino = t["solar_usada_kw"] + t["solar_bateria_kw"] + t["excedente_kw"]
    assert (destino - t["solar_kw"]).abs().max() < 1e-6
    assert (t["entregue_kw"] <= t["alocada_kw"] + 1e-9).all()
    assert (t["alocada_kw"] <= t["desejada_kw"] + 1e-9).all()
    assert ((t["solar_bateria_kw"] > 1e-9) & (t["bateria_kw"] > 1e-9)).sum() == 0
    if codigo != "A":
        assert (t["rede_kw"] <= PADRAO.limite_kw + 1e-6).all()
    if ESTRATEGIAS[codigo].bateria:
        assert t["soc_bateria"].between(cfg.BATERIA_SOC_MIN - 1e-9, 1 + 1e-9).all()
    else:
        assert (t["bateria_kw"] == 0).all() and t["soc_bateria"].isna().all()
    if not ESTRATEGIAS[codigo].usa_solar:
        assert (t["solar_kw"] == 0).all()


@pytest.mark.parametrize("codigo", ["C", "D"])
def test_balanco_de_energia_da_bateria_no_dia(demo, codigo):
    t = demo[codigo].telemetria
    entrou = (t["solar_bateria_kw"] * H).sum() * cfg.BATERIA_EFICIENCIA
    saiu = (t["bateria_kw"] * H).sum()
    variacao = (t["soc_bateria"].iloc[-1] - cfg.BATERIA_SOC_INICIAL) * cfg.BATERIA_KWH
    assert entrou - saiu == pytest.approx(variacao, abs=1e-6)


def test_energia_e_renovavel_das_sessoes_batem_com_a_telemetria(demo):
    for res in demo.values():
        t = res.telemetria
        assert sum(s.energia_kwh for s in res.sessoes) == pytest.approx(
            (t["entregue_kw"] * H).sum(), abs=1e-6
        )
        renovavel = ((t["solar_usada_kw"] + t["bateria_kw"]) * H).sum()
        assert sum(s.energia_renovavel_kwh for s in res.sessoes) == pytest.approx(
            renovavel, abs=1e-6
        )


def test_log_ocpp_e_coerente_com_as_sessoes(demo):
    for res in demo.values():
        contagem = res.ocpp.contar_por_acao()
        assert contagem["StartTransaction"] == len(res.sessoes)
        assert contagem["StopTransaction"] == len(res.sessoes)
        assert contagem.get("MeterValues", 0) > 0


def test_sem_gestao_passa_do_limite_e_a_solucao_final_nao(demo):
    a, d = metricas(demo["A"]), metricas(demo["D"])
    assert a["minutos_acima_limite"] > 0 and a["minutos_acima_disponivel"] > 0
    assert d["minutos_acima_limite"] == 0


def test_cenario_de_demonstracao_segue_a_regra_documentada(demo):
    m = {c: metricas(r) for c, r in demo.items()}
    assert m["A"]["minutos_acima_limite"] >= 30
    assert m["B"]["minutos_reduzidos"] >= 30
    assert (
        m["A"]["custo_rede_brl"]
        > m["B"]["custo_rede_brl"]
        > m["C"]["custo_rede_brl"]
        > m["D"]["custo_rede_brl"]
    )
    assert m["D"]["pct_promessas"] >= max(m["B"]["pct_promessas"], m["C"]["pct_promessas"])
    assert m["D"]["sessoes"] >= 8
    ponta = demo["D"].telemetria[demo["D"].telemetria["posto"] == "ponta"]
    assert ponta["soc_bateria_antes"].iloc[0] >= 0.9
    assert demo["D"].ocpp.contar_por_acao().get("SetChargingProfile", 0) > 0


def test_d_leva_energia_solar_para_a_ponta_e_compra_menos_rede_na_ponta(demo):
    c, d = metricas(demo["C"]), metricas(demo["D"])
    assert d["energia_rede_ponta_kwh"] < c["energia_rede_ponta_kwh"]
    t = demo["D"].telemetria
    na_ponta = (t.loc[t["posto"] == "ponta", "bateria_kw"] * H).sum()
    assert na_ponta >= 0.8 * (cfg.BATERIA_KWH * (1 - cfg.BATERIA_SOC_MIN))


def test_sem_bateria_na_instalacao_c_e_d_ficam_sem_soc():
    res = simular_dia(cfg.SEED_DEMO, FINAL, PADRAO.com(bateria_kwh=0.0))
    assert res.telemetria["soc_bateria"].isna().all()
    assert (res.telemetria["bateria_kw"] == 0).all()


def test_sem_gestao_nao_usa_solar_nem_corta():
    t = simular_dia(cfg.SEED_DEMO, SEM_GESTAO).telemetria
    assert (t["solar_kw"] == 0).all() and not t["em_corte"].any()


def test_ao_vivo_e_chamado_uma_vez_por_tick_com_eventos():
    chamadas = []
    simular_dia(cfg.SEED_DEMO, ao_vivo=lambda linha, eventos: chamadas.append((linha, eventos)))
    assert len(chamadas) == cfg.TICKS_POR_DIA
    assert any(eventos for _, eventos in chamadas)
    assert {"hora", "solar_kw", "rede_kw", "soc_bateria", "posto"} <= set(chamadas[0][0])
