import json

import pytest

from chargegrid import config as cfg
from chargegrid.estrategias import SPRINT3
from chargegrid.exportar import CAMPOS_PONTO, CAMPOS_RESUMO, para_energy_flow, salvar_energy_flow
from chargegrid.simulacao import simular_dia


@pytest.fixture(scope="module")
def fluxo():
    return para_energy_flow(simular_dia(cfg.SEED_DEMO))


def test_estrutura_segue_o_energy_flow_response_do_challenge(fluxo):
    assert set(fluxo) == {"inverter", "battery", "latest", "series", "today"}
    assert len(fluxo["series"]) == cfg.TICKS_POR_DIA
    assert all(tuple(p) == CAMPOS_PONTO for p in fluxo["series"])
    assert tuple(fluxo["today"]) == CAMPOS_RESUMO
    assert fluxo["battery"]["dispatch_mode"] == "peak_reserve"


def test_sinal_da_bateria_e_balanco_de_cada_ponto(fluxo):
    for p in fluxo["series"]:
        assert p["battery_kw"] == pytest.approx(
            p["battery_to_load_kw"] - p["solar_to_battery_kw"], abs=2e-3
        )
        origem = p["solar_to_load_kw"] + p["battery_to_load_kw"] + p["grid_to_load_kw"]
        assert origem == pytest.approx(p["load_kw"], abs=3e-3)


def test_resumo_do_dia_fecha(fluxo):
    hoje = fluxo["today"]
    soma = hoje["solar_to_load_kwh"] + hoje["battery_to_load_kwh"] + hoje["grid_to_load_kwh"]
    assert soma == pytest.approx(hoje["load_kwh"], abs=0.01)
    assert hoje["readings_count"] == cfg.TICKS_POR_DIA


def test_sem_bateria_o_campo_vem_nulo_e_o_arquivo_e_json_valido(tmp_path):
    res = simular_dia(cfg.SEED_DEMO, SPRINT3)
    caminho = salvar_energy_flow(res, tmp_path / "fluxo.json")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["battery"] is None
    assert all(p["battery_soc_pct"] is None for p in dados["series"])
