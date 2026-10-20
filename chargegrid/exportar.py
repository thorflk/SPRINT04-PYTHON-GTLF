"""Exporta o dia no contrato de dados do ChargeGrid-Manager (o Challenge).

O arquivo segue `EnergyFlowResponse` de `backend/app/schemas/energy.py` do Challenge: a mesma
estrutura que a API devolve para a tela "Fluxo de energia" do portal do proprietário. Assim, o
motor de simulação e despacho deste repositório produz dados que o backend e o frontend do
Challenge já sabem exibir. Convenção de sinal da bateria igual à do SEMS+: positivo =
descarregando, negativo = carregando. Potências em kW, energias em kWh, 3 casas.
"""

import json
from datetime import timedelta
from pathlib import Path

from chargegrid import config as cfg
from chargegrid.simulacao import ResultadoDia

# Campos de `EnergyFlowPoint` e `EnergySummary` no Challenge (conferidos nos testes).
CAMPOS_PONTO = (
    "timestamp",
    "load_kw",
    "solar_kw",
    "solar_to_load_kw",
    "battery_to_load_kw",
    "grid_to_load_kw",
    "solar_to_battery_kw",
    "solar_surplus_kw",
    "battery_kw",
    "battery_soc_pct",
    "grid_limit_kw",
    "demand_limited_kw",
)
CAMPOS_RESUMO = (
    "from_date",
    "to_date",
    "load_kwh",
    "solar_generated_kwh",
    "solar_to_load_kwh",
    "battery_to_load_kwh",
    "grid_to_load_kwh",
    "solar_to_battery_kwh",
    "solar_surplus_kwh",
    "renewable_share_pct",
    "peak_load_kw",
    "peak_grid_kw",
    "readings_count",
)


def _r(valor: float) -> float:
    return round(float(valor), 3)


def para_energy_flow(res: ResultadoDia) -> dict:
    t = res.telemetria
    h = cfg.PASSO_MIN / 60
    serie = []
    for linha in t.itertuples(index=False):
        instante = cfg.DATA_SIMULADA + timedelta(minutes=linha.minuto + cfg.PASSO_MIN)
        soc = linha.soc_bateria
        serie.append(
            {
                "timestamp": instante.strftime("%Y-%m-%dT%H:%M:%S"),
                "load_kw": _r(linha.entregue_kw),
                "solar_kw": _r(linha.solar_kw),
                "solar_to_load_kw": _r(linha.solar_usada_kw),
                "battery_to_load_kw": _r(linha.bateria_kw),
                "grid_to_load_kw": _r(linha.rede_kw),
                "solar_to_battery_kw": _r(linha.solar_bateria_kw),
                "solar_surplus_kw": _r(linha.excedente_kw),
                "battery_kw": _r(linha.bateria_kw - linha.solar_bateria_kw),
                "battery_soc_pct": None if soc != soc else round(100 * soc, 2),
                "grid_limit_kw": _r(linha.limite_kw),
                "demand_limited_kw": _r(linha.desejada_kw - linha.alocada_kw),
            }
        )
    kwh = lambda coluna: _r((t[coluna] * h).sum())  # noqa: E731
    carga = kwh("entregue_kw")
    renovavel = kwh("solar_usada_kw") + kwh("bateria_kw")
    dia = cfg.DATA_SIMULADA.date().isoformat()
    inversor = {
        "kind": "inverter",
        "sems_serial": "SIM-INV-001",
        "model": "Inversor híbrido GoodWe (simulado)",
        "rated_kw": res.instalacao.solar_kwp,
    }
    bateria = None
    if res.estrategia.bateria is not None:
        bateria = {
            "kind": "battery",
            "sems_serial": "SIM-BAT-001",
            "model": "Bateria GoodWe (simulada)",
            "capacity_kwh": res.instalacao.bateria_kwh,
            "max_charge_kw": res.instalacao.bateria_kw,
            "max_discharge_kw": res.instalacao.bateria_kw,
            "min_soc_pct": 100 * cfg.BATERIA_SOC_MIN,
            # o modo preditivo é o equivalente, aqui, ao "peak_reserve" do Challenge
            "dispatch_mode": "peak_reserve"
            if res.estrategia.bateria == "preditiva"
            else "self_consumption",
        }
    return {
        "inverter": inversor if res.estrategia.usa_solar else None,
        "battery": bateria,
        "latest": serie[-1] if serie else None,
        "series": serie,
        "today": {
            "from_date": dia,
            "to_date": dia,
            "load_kwh": carga,
            "solar_generated_kwh": kwh("solar_kw"),
            "solar_to_load_kwh": kwh("solar_usada_kw"),
            "battery_to_load_kwh": kwh("bateria_kw"),
            "grid_to_load_kwh": kwh("rede_kw"),
            "solar_to_battery_kwh": kwh("solar_bateria_kw"),
            "solar_surplus_kwh": kwh("excedente_kw"),
            "renewable_share_pct": round(100 * renovavel / carga, 2) if carga else None,
            "peak_load_kw": _r(t["entregue_kw"].max()),
            "peak_grid_kw": _r(t["rede_kw"].max()),
            "readings_count": len(serie),
        },
    }


def salvar_energy_flow(res: ResultadoDia, caminho: Path | str) -> Path:
    caminho = Path(caminho)
    caminho.write_text(
        json.dumps(para_energy_flow(res), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return caminho
