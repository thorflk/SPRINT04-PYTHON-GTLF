"""Previsão estatística de pico de demanda (média histórica por hora do dia).

NÃO é aprendizado de máquina: agrega N dias simulados, calcula média e desvio da potência
DESEJADA por hora e aponta a janela de maior demanda. O Challenge usa Prophet no microsserviço
`ia/`; aqui o objetivo é demonstrar o padrão (sazonalidade horária) com pandas. Um backtest
compara o modelo com um baseline constante em dia não visto no ajuste.

Sprint 4: a previsão deixou de ser só informativa. A demanda prevista por hora alimenta o
despacho preditivo da bateria (`despacho.reserva_para_pico_kwh`), que guarda energia para as
horas em que a demanda deve passar do limite da rede.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import pandas as pd

from chargegrid import config as cfg
from chargegrid.estrategias import SPRINT3
from chargegrid.formato import br
from chargegrid.simulacao import simular_dia
from chargegrid.tarifacao import em_reais


@dataclass(frozen=True)
class Previsao:
    por_hora: pd.DataFrame
    janela_pico: tuple[int, int, float]  # (hora_inicio, hora_fim_exclusiva, media_kw)
    melhores_horas: list[int]


def gerar_historico(n_dias: int, seed_base: int = cfg.SEED_HISTORICO_BASE) -> list[pd.DataFrame]:
    """Dias passados, operados como na Sprint 3 (o histórico existe antes da bateria)."""
    return [simular_dia(seed_base + i, SPRINT3).telemetria for i in range(1, n_dias + 1)]


@lru_cache(maxsize=4)
def _demanda_prevista(n_dias: int) -> tuple[float, ...]:
    return tuple(ajustar(gerar_historico(n_dias)).por_hora["media_kw"].tolist())


def demanda_prevista_padrao(n_dias: int = cfg.DIAS_HISTORICO) -> list[float]:
    """Demanda média prevista por hora (24 valores, kW). Calculada uma vez e reaproveitada."""
    return list(_demanda_prevista(n_dias))


def ajustar(historico: list[pd.DataFrame]) -> Previsao:
    dias = pd.concat([df.assign(dia=i) for i, df in enumerate(historico)], ignore_index=True)
    dias["hora"] = dias["minuto"] // 60
    por_dia_hora = (
        dias.groupby(["dia", "hora"])
        .agg(desejada=("desejada_kw", "mean"), solar=("solar_kw", "mean"))
        .reset_index()
    )
    por_hora = (
        por_dia_hora.groupby("hora")
        .agg(
            media_kw=("desejada", "mean"),
            desvio_kw=("desejada", "std"),
            solar_medio_kw=("solar", "mean"),
        )
        .reindex(range(24), fill_value=0.0)
        .rename_axis("hora")
        .reset_index()
    )
    por_hora["desvio_kw"] = por_hora["desvio_kw"].fillna(0.0)
    return Previsao(por_hora, _janela_de_pico(por_hora), _melhores_horas(por_hora))


def _janela_de_pico(por_hora: pd.DataFrame) -> tuple[int, int, float]:
    medias = por_hora["media_kw"].tolist()
    largura = cfg.LARGURA_JANELA_PICO_H
    melhor_inicio, melhor_media = 0, -1.0
    for inicio in range(0, 24 - largura + 1):
        media = sum(medias[inicio : inicio + largura]) / largura
        if media > melhor_media:
            melhor_inicio, melhor_media = inicio, media
    return melhor_inicio, melhor_inicio + largura, melhor_media


def _melhores_horas(por_hora: pd.DataFrame) -> list[int]:
    candidatas = por_hora[
        (por_hora["solar_medio_kw"] >= cfg.SOLAR_MINIMO_RECOMENDACAO_KW)
        & ~por_hora["hora"].between(cfg.HORA_PICO_INICIO, cfg.HORA_PICO_FIM - 1)
    ]
    escolhidas = candidatas.sort_values(["media_kw", "hora"]).head(cfg.TOP_HORAS_RECOMENDADAS)
    return sorted(int(h) for h in escolhidas["hora"])


def backtest(prev: Previsao, telemetria_real: pd.DataFrame) -> dict[str, float]:
    real = (
        telemetria_real.assign(hora=telemetria_real["minuto"] // 60)
        .groupby("hora")["desejada_kw"]
        .mean()
        .reindex(range(24), fill_value=0.0)
    )
    previsto = prev.por_hora.set_index("hora")["media_kw"].reindex(range(24), fill_value=0.0)
    constante = float(previsto.mean())
    return {
        "mae_kw": round(float((previsto - real).abs().mean()), 3),
        "mae_baseline_kw": round(float((constante - real).abs().mean()), 3),
    }


def _sobreposicao_com_tarifa_de_pico(inicio: int, fim: int) -> str:
    """Compara a janela de pico de demanda com a faixa de tarifa de pico, sem exagerar."""
    faixa = f"{cfg.HORA_PICO_INICIO}h–{cfg.HORA_PICO_FIM}h"
    tarifa_pico = f"R$ {br(float(cfg.TARIFA_PICO))}/kWh"
    tarifa_normal = f"R$ {br(float(cfg.TARIFA_NORMAL))}/kWh"
    janela = range(inicio, fim)
    cobertas = [h for h in janela if cfg.HORA_PICO_INICIO <= h < cfg.HORA_PICO_FIM]
    if len(cobertas) == len(janela):
        return f"A tarifa de pico ({tarifa_pico}, {faixa}) cobre toda essa janela."
    if cobertas:
        return (
            f"A tarifa de pico ({tarifa_pico}, {faixa}) cobre só parte dessa janela; "
            f"nas demais horas é {tarifa_normal} — vale avaliar estender a faixa de pico."
        )
    return (
        f"Essa janela não coincide com a faixa de tarifa de pico ({faixa}): "
        "a tarifa atual não incentiva deslocar esse consumo."
    )


def recomendacoes(prev: Previsao, limite_kw: float) -> list[str]:
    inicio, fim, media = prev.janela_pico
    pct = 100 * media / limite_kw
    textos = [
        f"Pico previsto entre {inicio}h e {fim}h: demanda média de {br(media, 1)} kW "
        f"({br(pct, 0)}% do limite de {br(limite_kw, 0)} kW)."
    ]
    textos.append(_sobreposicao_com_tarifa_de_pico(inicio, fim))
    horas = ", ".join(f"{h}h" for h in prev.melhores_horas)
    textos.append(
        f"Melhores horários para recarregar: {horas} — menor ocupação prevista, "
        "tarifa normal e geração solar disponível."
    )
    economia = em_reais(Decimal(30) * (cfg.TARIFA_PICO - cfg.TARIFA_NORMAL))
    textos.append(
        f"Exemplo: deslocar uma recarga de 30 kWh do pico para esses horários "
        f"economiza R$ {br(float(economia))}."
    )
    return textos
