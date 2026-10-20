"""Sessões de recarga: curva de potência por SoC, chegadas do dia e prazo de saída.

Curva (adaptada de `curve_engine.py` do Challenge): platô em min(nominal, OBC) até 80% de SoC;
depois decai linearmente até 10% da nominal em 100%. A rampa inicial de 2 min do Challenge é
desprezada porque o passo da simulação é de 5 min.

Sprint 4: cada motorista informa quanto tempo fica no shopping. O carro ocupa o ponto até sair
(mesmo depois de carregado) e o sistema PROMETE o SoC que o carro alcançaria nesse tempo com
85% da potência máxima do ponto (limitado ao alvo pedido). Como as chegadas, os pontos e as
saídas não dependem da estratégia de controle, o MESMO dia de demanda pode ser simulado em
todos os cenários.
"""

import math
import random
from dataclasses import dataclass, field
from decimal import Decimal

from chargegrid import config as cfg
from chargegrid.veiculos import Veiculo, escolher_veiculo

HORAS_PASSO = cfg.PASSO_MIN / 60


def potencia_desejada_kw(nominal_kw: float, veiculo: Veiculo, soc: float) -> float:
    plato = min(nominal_kw, veiculo.obc_kw)
    if soc < cfg.SOC_INICIO_TAPER:
        return plato
    fim = min(cfg.TAPER_FIM_FRACAO_NOMINAL * nominal_kw, plato)
    fracao = min(1.0, (soc - cfg.SOC_INICIO_TAPER) / (1.0 - cfg.SOC_INICIO_TAPER))
    return plato - (plato - fim) * fracao


def soc_alcancavel(
    nominal_kw: float, veiculo: Veiculo, soc: float, ticks: int, fator: float = 1.0
) -> float:
    """SoC que o carro atinge em `ticks` intervalos com `fator` x a potência máxima."""
    for _ in range(ticks):
        potencia = potencia_desejada_kw(nominal_kw, veiculo, soc) * fator
        soc = min(1.0, soc + potencia * HORAS_PASSO / veiculo.bateria_kwh)
    return soc


@dataclass(frozen=True)
class Chegada:
    tick: int
    veiculo: Veiculo
    soc_inicial: float
    alvo_pedido: float
    tick_saida: int  # exclusivo: o carro já saiu no início deste tick
    preferencia: tuple[str, ...]  # ordem em que o motorista escolhe entre os pontos livres


@dataclass
class Sessao:
    id: int
    ponto: str
    veiculo: Veiculo
    soc_inicial: float
    alvo: float  # SoC prometido (o que dá para entregar no tempo de permanência)
    tick_inicio: int
    tick_saida: int
    alvo_pedido: float = 1.0
    soc: float = field(init=False)
    tick_fim: int | None = None
    concluida: bool = False  # atingiu o SoC prometido antes de sair
    energia_kwh: float = 0.0
    energia_renovavel_kwh: float = 0.0
    energia_pico_kwh: float = 0.0
    custo: Decimal = Decimal("0")
    custo_pico: Decimal = Decimal("0")
    ticks_em_corte: int = 0

    def __post_init__(self) -> None:
        self.soc = self.soc_inicial

    @property
    def atingiu_alvo(self) -> bool:
        return self.soc >= self.alvo - 1e-6

    @property
    def falta_kwh(self) -> float:
        return max(0.0, (self.alvo - self.soc) * self.veiculo.bateria_kwh)

    def potencia_desejada_kw(self, nominal_kw: float) -> float:
        if self.atingiu_alvo:
            return 0.0
        return potencia_desejada_kw(nominal_kw, self.veiculo, self.soc)

    def horas_restantes(self, tick: int) -> float:
        return max(0, self.tick_saida - tick) * HORAS_PASSO

    def folga_h(self, tick: int, nominal_kw: float) -> float:
        """Tempo que sobra até a saída depois de carregar o que falta na potência máxima."""
        potencia = self.potencia_desejada_kw(nominal_kw)
        if potencia <= 0:
            return self.horas_restantes(tick)
        return self.horas_restantes(tick) - self.falta_kwh / potencia

    def piso_kw(self, tick: int, nominal_kw: float, margem: float) -> float:
        """Menor potência AGORA que ainda permite cumprir a promessa até a saída, supondo que
        no futuro o carro só consiga `margem` x a potência da curva (agendamento "o mais tarde
        possível", com menor folga primeiro). Considera a desaceleração acima de 80% de SoC."""
        potencia = self.potencia_desejada_kw(nominal_kw)
        if potencia <= 0:
            return 0.0
        # termina um intervalo antes da saída: margem contra arredondamentos
        ticks_futuros = max(0, self.tick_saida - tick - 2)
        soc_futuro = soc_alcancavel(nominal_kw, self.veiculo, self.soc, ticks_futuros, margem)
        futuro_kwh = (soc_futuro - self.soc) * self.veiculo.bateria_kwh
        return min(potencia, max(0.0, self.falta_kwh - futuro_kwh) / HORAS_PASSO)

    def avancar(self, potencia_alocada_kw: float) -> float:
        """Entrega energia por um intervalo e devolve os kWh entregues (limitados ao alvo)."""
        if potencia_alocada_kw < 0:
            raise ValueError("potencia_alocada_kw não pode ser negativa")
        energia = min(potencia_alocada_kw * HORAS_PASSO, self.falta_kwh)
        self.soc += energia / self.veiculo.bateria_kwh
        self.energia_kwh += energia
        return energia

    def registrar(
        self,
        energia_kwh: float,
        fracao_renovavel: float,
        custo: Decimal,
        em_pico: bool,
        em_corte: bool,
    ) -> None:
        self.energia_renovavel_kwh += energia_kwh * fracao_renovavel
        self.custo += custo
        if em_pico:
            self.energia_pico_kwh += energia_kwh
            self.custo_pico += custo
        if em_corte:
            self.ticks_em_corte += 1


def criar_sessao(id: int, ponto: str, chegada: Chegada) -> Sessao:
    nominal = cfg.PONTOS[ponto]
    ticks = chegada.tick_saida - chegada.tick
    possivel = soc_alcancavel(
        nominal, chegada.veiculo, chegada.soc_inicial, ticks, cfg.FATOR_PROMESSA
    )
    alvo = min(chegada.alvo_pedido, math.floor(possivel * 10_000) / 10_000)  # nunca acima
    return Sessao(
        id,
        ponto,
        chegada.veiculo,
        chegada.soc_inicial,
        alvo,
        chegada.tick,
        chegada.tick_saida,
        chegada.alvo_pedido,
    )


def gerar_chegadas(
    rng: random.Random, faixa: tuple[int, int] = cfg.SESSOES_POR_PONTO_DIA
) -> list[Chegada]:
    """Chegadas do dia, sorteadas pelo perfil horário do shopping, em ordem de tempo."""
    total = sum(rng.randint(*faixa) for _ in cfg.PONTOS)
    pesos = [
        cfg.PESOS_CHEGADA_POR_HORA[(t * cfg.PASSO_MIN) // 60] for t in range(cfg.TICKS_POR_DIA)
    ]
    ticks = sorted(rng.choices(range(cfg.TICKS_POR_DIA), weights=pesos, k=total))
    chegadas = []
    for tick in ticks:
        veiculo = escolher_veiculo(rng)
        soc_inicial = round(rng.uniform(cfg.SOC_INICIAL_MIN, cfg.SOC_INICIAL_MAX), 2)
        alvo = rng.choice(cfg.ALVOS_SOC)
        permanencia = round(rng.uniform(*cfg.PERMANENCIA_H) * 60 / cfg.PASSO_MIN)
        saida = min(tick + max(1, permanencia), cfg.TICKS_POR_DIA)
        preferencia = tuple(rng.sample(list(cfg.PONTOS), k=len(cfg.PONTOS)))
        chegadas.append(Chegada(tick, veiculo, soc_inicial, alvo, saida, preferencia))
    return chegadas
