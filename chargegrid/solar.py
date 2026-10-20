"""Geração fotovoltaica simulada (inversor GoodWe + módulos) — PREMISSA DO GRUPO.

Curva em sen² entre o nascer e o poente, multiplicada por um fator de nuvem por intervalo.
Potência de pico = kWp × derate (perdas de sistema).
"""

import math
import random

from chargegrid import config as cfg


def potencia_solar_kw(
    minuto_do_dia: int, fator_nuvem: float = 1.0, kwp: float = cfg.SOLAR_KWP
) -> float:
    hora = minuto_do_dia / 60
    if hora <= cfg.SOLAR_NASCER_H or hora >= cfg.SOLAR_POENTE_H:
        return 0.0
    x = (hora - cfg.SOLAR_NASCER_H) / (cfg.SOLAR_POENTE_H - cfg.SOLAR_NASCER_H)
    return kwp * cfg.SOLAR_DERATE * math.sin(math.pi * x) ** 2 * fator_nuvem


def gerar_fatores_nuvem(rng: random.Random) -> list[float]:
    """Um fator (0,35–1,0) por tick: eventos de nuvem de 2 a 8 intervalos, ao acaso."""
    fatores = [1.0] * cfg.TICKS_POR_DIA
    tick = 0
    while tick < cfg.TICKS_POR_DIA:
        if rng.random() < cfg.PROB_NUVEM:
            duracao = rng.randint(2, 8)
            fator = rng.uniform(0.35, 0.7)
            for i in range(tick, min(tick + duracao, cfg.TICKS_POR_DIA)):
                fatores[i] = fator
            tick += duracao
        else:
            tick += 1
    return fatores
