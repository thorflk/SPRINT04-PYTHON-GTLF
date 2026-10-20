"""Estratégias de operação (cenários A a D) e parâmetros da instalação.

O MESMO dia de demanda é simulado em cada estratégia; só muda a gestão de energia. Cada
cenário acrescenta uma peça ao anterior, para medir a contribuição de cada uma:

  A  Sem gestão        rede pura, sem limite: como um eletroposto comum funciona hoje
  B  Sprint 3          + usina solar + controle de demanda proporcional
  C  + bateria         + bateria em autoconsumo (descarrega sempre que falta sol)
  D  Solução final     bateria com despacho PREDITIVO + agendamento por folga
"""

from dataclasses import dataclass, replace

from chargegrid import config as cfg


@dataclass(frozen=True)
class Estrategia:
    codigo: str
    nome: str
    usa_solar: bool
    controle: str  # "nenhum" | "proporcional" | "folga"
    bateria: str | None  # None | "autoconsumo" | "preditiva"


SEM_GESTAO = Estrategia("A", "Sem gestão", False, "nenhum", None)
SPRINT3 = Estrategia("B", "Solar + controle (Sprint 3)", True, "proporcional", None)
BATERIA_SIMPLES = Estrategia("C", "+ Bateria (autoconsumo)", True, "proporcional", "autoconsumo")
FINAL = Estrategia("D", "Solução final (preditiva)", True, "folga", "preditiva")

ESTRATEGIAS: dict[str, Estrategia] = {
    e.codigo: e for e in (SEM_GESTAO, SPRINT3, BATERIA_SIMPLES, FINAL)
}


@dataclass(frozen=True)
class Instalacao:
    """Parâmetros que o painel interativo deixa variar. Padrões em `config.py`."""

    solar_kwp: float = cfg.SOLAR_KWP
    bateria_kwh: float = cfg.BATERIA_KWH
    bateria_kw: float = cfg.BATERIA_KW
    carga_disponivel_kw: float = cfg.CARGA_DISPONIVEL_KW

    @property
    def limite_kw(self) -> float:
        return self.carga_disponivel_kw * cfg.MARGEM_SEGURANCA

    def com(self, **mudancas) -> "Instalacao":
        return replace(self, **mudancas)


PADRAO = Instalacao()
