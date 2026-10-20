"""Tarifação por faixa horária: preço ao motorista e custo da rede para o operador.

Há duas tabelas. O motorista paga a tarifa da Sprint 2 (pico 18h-21h). O operador compra a
energia da rede pela Tarifa Branca da distribuidora (ponta 17h30-20h30, com postos
intermediários antes e depois). Como o kWh da ponta custa mais ao operador (R$ 1,56) do que o
motorista paga no pico (R$ 1,40), toda recarga feita com energia da rede na ponta dá prejuízo:
é esse sinal que o despacho da bateria e o agendamento da Sprint 4 aproveitam.

Convenção de dinheiro herdada de `services/pricing.py` do Challenge: `Decimal`, arredondamento
`ROUND_HALF_UP`, 4 casas internas. Cada intervalo de 5 min é cobrado pela tarifa vigente no
seu início, então uma sessão que atravessa as 18h paga cada parte na faixa correta.
"""

from decimal import ROUND_HALF_UP, Decimal

from chargegrid import config as cfg

_CASAS_4 = Decimal("0.0001")
_CASAS_2 = Decimal("0.01")


def eh_pico(minuto_do_dia: int) -> bool:
    hora = minuto_do_dia // 60
    return cfg.HORA_PICO_INICIO <= hora < cfg.HORA_PICO_FIM


def tarifa_no_instante(minuto_do_dia: int) -> Decimal:
    return cfg.TARIFA_PICO if eh_pico(minuto_do_dia) else cfg.TARIFA_NORMAL


def custo_do_intervalo(energia_kwh: float, minuto_do_dia: int) -> Decimal:
    if energia_kwh < 0:
        raise ValueError("energia_kwh não pode ser negativa")
    custo = Decimal(str(energia_kwh)) * tarifa_no_instante(minuto_do_dia)
    return custo.quantize(_CASAS_4, rounding=ROUND_HALF_UP)


def em_reais(valor: Decimal) -> Decimal:
    return valor.quantize(_CASAS_2, rounding=ROUND_HALF_UP)


def posto_tarifario(minuto_do_dia: int) -> str:
    """Posto da Tarifa Branca no minuto: "ponta", "intermediario" ou "fora_ponta"."""
    inicio, fim = cfg.PONTA_MIN
    if inicio <= minuto_do_dia < fim:
        return "ponta"
    if any(a <= minuto_do_dia < b for a, b in cfg.INTERMEDIARIO_MIN):
        return "intermediario"
    return "fora_ponta"


def custo_rede_kwh(minuto_do_dia: int) -> Decimal:
    return {
        "ponta": cfg.CUSTO_REDE_PONTA,
        "intermediario": cfg.CUSTO_REDE_INTERMEDIARIO,
        "fora_ponta": cfg.CUSTO_REDE_FORA_PONTA,
    }[posto_tarifario(minuto_do_dia)]


def custo_rede_do_intervalo(energia_kwh: float, minuto_do_dia: int) -> Decimal:
    if energia_kwh < 0:
        raise ValueError("energia_kwh não pode ser negativa")
    custo = Decimal(str(energia_kwh)) * custo_rede_kwh(minuto_do_dia)
    return custo.quantize(_CASAS_4, rounding=ROUND_HALF_UP)
