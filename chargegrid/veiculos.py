"""Catálogo simplificado de veículos e limite de carregador de bordo (OBC).

O gargalo de uma recarga AC costuma ser o carro, não o carregador: um veículo com OBC de
7,4 kW num ponto de 22 kW carrega a 7,4 kW. Valores adaptados de `simulador/vehicles.py` do
Challenge (aproximações de mercado, só para simulação). O Renault Zoe (22 kW AC) é PREMISSA
DO GRUPO, incluído para o ponto P3 poder operar na potência nominal.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Veiculo:
    nome: str
    obc_kw: float
    bateria_kwh: float


CATALOGO: tuple[Veiculo, ...] = (
    Veiculo("Nissan Leaf", 6.6, 40.0),
    Veiculo("Chevrolet Bolt EV", 7.4, 60.0),
    Veiculo("BYD Dolphin", 7.0, 44.9),
    Veiculo("Renault Kwid E-Tech", 6.6, 26.8),
    Veiculo("BYD Song Plus", 11.0, 71.8),
    Veiculo("Volvo XC40 Recharge", 11.0, 78.0),
    Veiculo("Renault Zoe", 22.0, 52.0),
)


def escolher_veiculo(rng: random.Random) -> Veiculo:
    return rng.choice(CATALOGO)
