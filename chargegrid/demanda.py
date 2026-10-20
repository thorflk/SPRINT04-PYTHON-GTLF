"""Controle de demanda: distribui a potência entre os pontos ativos.

O limite contratado vale para a IMPORTAÇÃO da rede. A geração solar atende os carregadores
primeiro, então o teto de potência para os veículos é `limite + solar`. Se a soma desejada
excede o teto, aplica-se o mesmo fator proporcional da Sprint 2 a todos os pontos.

Sprint 4 — agendamento inteligente (`alocar_por_folga`). Em vez de cortar todos por igual:
  1. cada carro recebe primeiro o seu PISO, a potência mínima que ainda garante a carga
     prometida até a hora de saída (ver `Sessao.piso_kw`);
  2. o que sobra do teto vai para quem tem MENOR FOLGA (quem sai mais cedo ou falta mais);
  3. na ponta da distribuidora, a sobra é limitada a um ORÇAMENTO (energia renovável
     disponível): quem tem folga é adiado para depois da ponta, quando o kWh da rede é mais
     barato, sem deixar de receber a carga prometida.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Alocacao:
    teto_kw: float
    desejada_total_kw: float
    fator: float
    alocadas: dict[str, float]

    @property
    def em_corte(self) -> bool:
        return self.fator < 1.0

    @property
    def alocada_total_kw(self) -> float:
        return sum(self.alocadas.values())


def _truncar_mw(valor_kw: float) -> float:
    """Trunca (nunca arredonda para cima) a 3 casas, para a soma não passar do teto."""
    return math.floor(valor_kw * 1000 + 1e-9) / 1000


def alocar(desejadas: dict[str, float], solar_kw: float, limite_kw: float) -> Alocacao:
    teto = limite_kw + max(solar_kw, 0.0)
    total = sum(desejadas.values())
    if total <= teto or total <= 0:
        return Alocacao(teto, total, 1.0, dict(desejadas))
    fator = teto / total
    alocadas = {ponto: _truncar_mw(d * fator) for ponto, d in desejadas.items()}
    return Alocacao(teto, total, fator, alocadas)


@dataclass(frozen=True)
class Pedido:
    desejada_kw: float
    piso_kw: float
    folga_h: float


def alocar_por_folga(
    pedidos: dict[str, Pedido], teto_kw: float, orcamento_kw: float | None = None
) -> Alocacao:
    """Aloca pisos primeiro e a sobra por menor folga, sem passar de `teto_kw`.

    `orcamento_kw` (opcional, <= teto) limita só a sobra acima dos pisos: os pisos são sempre
    atendidos enquanto couberem no teto físico.
    """
    desejada_total = sum(p.desejada_kw for p in pedidos.values())
    teto = max(teto_kw, 0.0)
    pisos = {ponto: min(p.piso_kw, p.desejada_kw) for ponto, p in pedidos.items()}
    soma_pisos = sum(pisos.values())
    if soma_pisos > teto:  # nem os pisos cabem: corte proporcional sobre os pisos
        fator = teto / soma_pisos
        alocadas = {ponto: _truncar_mw(v * fator) for ponto, v in pisos.items()}
    else:
        alocadas = dict(pisos)
        limite_sobra = teto if orcamento_kw is None else min(teto, max(orcamento_kw, soma_pisos))
        sobra = limite_sobra - soma_pisos
        for ponto in sorted(pedidos, key=lambda p: (pedidos[p].folga_h, p)):
            extra = min(sobra, pedidos[ponto].desejada_kw - alocadas[ponto])
            if extra <= 0:
                continue
            alocadas[ponto] = _truncar_mw(alocadas[ponto] + extra)
            sobra -= extra
    alocada_total = sum(alocadas.values())
    fator = alocada_total / desejada_total if desejada_total > 0 else 1.0
    return Alocacao(teto, desejada_total, min(1.0, fator), alocadas)


def comandos_de_limite(
    ultimo_limite: dict[str, float | None],
    desejadas: dict[str, float],
    alocadas: dict[str, float],
    nominais: dict[str, float],
    tol_kw: float = 0.05,
) -> list[tuple[str, float]]:
    """Decide quais pontos recebem um novo `SetChargingProfile` neste intervalo.

    Envia o limite quando o ponto está cortado e o valor mudou mais que `tol_kw`; envia a
    liberação (limite nominal) quando o corte termina. Atualiza `ultimo_limite` (mutação).
    """
    comandos: list[tuple[str, float]] = []
    for ponto, desejada in desejadas.items():
        alocada = alocadas[ponto]
        anterior = ultimo_limite.get(ponto)
        if alocada < desejada - 1e-9:
            if anterior is None or abs(anterior - alocada) > tol_kw:
                comandos.append((ponto, alocada))
                ultimo_limite[ponto] = alocada
        elif anterior is not None:
            comandos.append((ponto, nominais[ponto]))
            ultimo_limite[ponto] = None
    return comandos
