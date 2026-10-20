"""Despacho de energia: de onde vem cada kW das recargas (solar -> bateria -> rede).

Função pura `despachar` (adaptada de `energy_dispatch.py` do Challenge) mais a política
PREDITIVA da Sprint 4, que decide QUANDO a bateria guarda e QUANDO entrega energia. A ideia:
um kWh solar usado direto no carro antes da ponta evita R$ 0,69 de rede; guardado e entregue na
ponta, evita R$ 1,56 x 0,90 de eficiência = R$ 1,40. Então a bateria deve chegar CHEIA à ponta,
mas sem desperdiçar sol:

  * Antes da ponta, a previsão estima a SOBRA de sol até a ponta (geração esperada menos a
    demanda prevista por hora). Se essa sobra não basta para encher a bateria, a parte que
    falta vai para a bateria ANTES dos carros, dividida igualmente pelas horas de sol que
    restam (taxa proporcional: sem liga-desliga); nesse meio-tempo os carros usam a rede barata.
    Se a sobra basta, os carros usam o sol agora e a bateria enche depois; a energia que vai
    ser reposta pode até ser descarregada antes da ponta.
  * Na ponta e depois dela, a bateria entrega o que tem, menos a RESERVA para cortar o pico:
    a energia que a previsão diz que a demanda vai passar do limite da rede.
  * A qualquer hora, se a carga passaria do limite da rede, a bateria cobre o excesso.
  * A bateria NUNCA carrega pela rede: o objetivo é deslocar energia renovável.
"""

import math
from dataclasses import dataclass

from chargegrid import config as cfg
from chargegrid.bateria import Bateria
from chargegrid.solar import potencia_solar_kw


@dataclass(frozen=True)
class Despacho:
    carga_kw: float
    solar_kw: float
    solar_para_carga_kw: float
    solar_para_bateria_kw: float
    bateria_para_carga_kw: float
    rede_kw: float
    excedente_kw: float

    @property
    def renovavel_kw(self) -> float:
        """A bateria só carrega com solar, então o que sai dela também é renovável."""
        return self.solar_para_carga_kw + self.bateria_para_carga_kw


def despachar(
    carga_kw: float,
    solar_kw: float,
    bateria: Bateria | None,
    limite_kw: float | None,
    horas: float,
    guardar_kw: float = 0.0,
    descarga_livre_kw: float = math.inf,
) -> Despacho:
    """Decide a origem da energia da `carga_kw` e aplica o resultado na bateria.

    `guardar_kw`: quanto do solar vai para a bateria antes da carga (nunca a ponto de empurrar
    a rede acima do limite). `descarga_livre_kw`: quanto a bateria pode entregar além do que
    passa do limite (infinito = autoconsumo; 0 = só corta pico). `limite_kw=None` = rede sem
    limite (cenário sem gestão).
    """
    carga_kw = max(0.0, carga_kw)
    solar_kw = max(0.0, solar_kw)
    pode_carregar = bateria.max_carga_kw(horas) if bateria else 0.0
    pode_descarregar = bateria.max_descarga_kw(horas) if bateria else 0.0

    solar_bat = min(solar_kw, pode_carregar, max(0.0, guardar_kw))
    solar_carga = min(solar_kw - solar_bat, carga_kw)
    deficit = carga_kw - solar_carga
    acima = max(0.0, deficit - limite_kw) if limite_kw is not None else 0.0
    if acima > 0 and solar_bat > 0:  # guardar energia não pode custar corte nos carros
        devolve = min(acima, solar_bat)
        solar_bat -= devolve
        solar_carga += devolve
        deficit -= devolve
        acima -= devolve

    bat_carga = 0.0
    if deficit > 0 and solar_bat == 0:
        bat_carga = min(max(acima, min(deficit, descarga_livre_kw)), pode_descarregar)
        deficit -= bat_carga
    sobra = solar_kw - solar_carga - solar_bat
    if sobra > 0 and bat_carga == 0:
        extra = min(sobra, pode_carregar - solar_bat)
        solar_bat += max(0.0, extra)
        sobra = solar_kw - solar_carga - solar_bat

    if bateria is not None:
        bateria.aplicar(solar_bat, bat_carga, horas)
    return Despacho(carga_kw, solar_kw, solar_carga, solar_bat, bat_carga, deficit, sobra)


# --- política preditiva ------------------------------------------------------------------


def antes_da_ponta(minuto_do_dia: int) -> bool:
    return minuto_do_dia < cfg.PONTA_MIN[0]


def na_ponta(minuto_do_dia: int) -> bool:
    return cfg.PONTA_MIN[0] <= minuto_do_dia < cfg.PONTA_MIN[1]


def reserva_para_pico_kwh(
    demanda_prevista_kw: list[float], minuto_do_dia: int, limite_kw: float, kwp: float
) -> float:
    """Energia que a bateria deve guardar para cortar o pico de HOJE a partir de agora.

    Soma, hora a hora, quanto a demanda prevista passa de `limite + solar de céu limpo` (só
    o restante da hora corrente conta). Vem da média histórica por hora de `previsao.py`.
    """
    total = 0.0
    hora_atual = minuto_do_dia // 60
    for hora in range(hora_atual, 24):
        solar = potencia_solar_kw(hora * 60 + 30, 1.0, kwp)
        excesso = max(0.0, demanda_prevista_kw[hora] - limite_kw - solar)
        fracao = (60 - minuto_do_dia % 60) / 60 if hora == hora_atual else 1.0
        total += excesso * fracao
    return total


def sobra_solar_prevista_kwh(
    demanda_prevista_kw: list[float], minuto_do_dia: int, kwp: float, eficiencia: float
) -> float:
    """Energia que a sobra de sol prevista ainda pode pôr na bateria até o início da ponta."""
    total = 0.0
    for minuto in range(minuto_do_dia, cfg.PONTA_MIN[0], cfg.PASSO_MIN):
        solar = potencia_solar_kw(minuto, cfg.FATOR_PREVISAO_SOLAR, kwp)
        total += max(0.0, solar - demanda_prevista_kw[minuto // 60]) * cfg.PASSO_MIN / 60
    return total * eficiencia


def plano_da_bateria(
    bateria: Bateria,
    minuto_do_dia: int,
    demanda_prevista_kw: list[float],
    limite_kw: float,
    kwp: float,
    horas_passo: float,
) -> tuple[bool, float, float]:
    """Decide o intervalo: (guardar_kw, descarga_livre_kw, reserva_para_pico_kwh)."""
    reserva = reserva_para_pico_kwh(demanda_prevista_kw, minuto_do_dia, limite_kw, kwp)
    if not antes_da_ponta(minuto_do_dia):
        livre = max(0.0, bateria.energia_util_kwh - reserva)
        return 0.0, livre / horas_passo, reserva
    espaco = bateria.capacidade_kwh * (1.0 - bateria.soc)
    sobra = sobra_solar_prevista_kwh(demanda_prevista_kw, minuto_do_dia, kwp, bateria.eficiencia)
    if sobra >= espaco:
        return 0.0, (sobra - espaco) / horas_passo, reserva
    horas_de_sol = horas_passo * sum(
        1
        for minuto in range(minuto_do_dia, cfg.PONTA_MIN[0], cfg.PASSO_MIN)
        if potencia_solar_kw(minuto, cfg.FATOR_PREVISAO_SOLAR, kwp) >= 1.0
    )
    if horas_de_sol <= 0:
        return 0.0, 0.0, reserva
    return (espaco - sobra) / (bateria.eficiencia * horas_de_sol), 0.0, reserva
