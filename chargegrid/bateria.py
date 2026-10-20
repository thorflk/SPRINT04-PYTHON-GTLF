"""Bateria estacionária atrás do inversor híbrido GoodWe — SIMULADA (PREMISSA DO GRUPO).

Só a física: limites de potência, SoC mínimo e perdas. Quem decide quanto carregar ou
descarregar é `despacho.py`. Convenção de perdas igual à do Challenge
(`backend/app/services/energy_dispatch.py`): a perda inteira de ida e volta é aplicada na carga
(energia guardada = potência x tempo x eficiência); a descarga entrega o que sai do SoC.
"""

from dataclasses import dataclass

from chargegrid import config as cfg


@dataclass
class Bateria:
    capacidade_kwh: float = cfg.BATERIA_KWH
    potencia_kw: float = cfg.BATERIA_KW
    eficiencia: float = cfg.BATERIA_EFICIENCIA
    soc_min: float = cfg.BATERIA_SOC_MIN
    soc: float = cfg.BATERIA_SOC_INICIAL

    def __post_init__(self) -> None:
        if self.capacidade_kwh <= 0 or self.potencia_kw < 0:
            raise ValueError("capacidade deve ser positiva e potência não negativa")
        if not 0 <= self.soc_min <= self.soc <= 1:
            raise ValueError("é preciso 0 <= soc_min <= soc <= 1")

    @property
    def energia_kwh(self) -> float:
        return self.capacidade_kwh * self.soc

    @property
    def energia_util_kwh(self) -> float:
        """Energia que ainda pode sair sem passar abaixo do SoC mínimo."""
        return max(0.0, self.capacidade_kwh * (self.soc - self.soc_min))

    def max_descarga_kw(self, horas: float) -> float:
        return min(self.potencia_kw, self.energia_util_kwh / horas)

    def max_carga_kw(self, horas: float) -> float:
        espaco_kwh = self.capacidade_kwh * (1.0 - self.soc)
        return min(self.potencia_kw, espaco_kwh / (horas * self.eficiencia))

    def aplicar(self, carga_kw: float, descarga_kw: float, horas: float) -> None:
        """Carrega OU descarrega durante `horas` (nunca os dois no mesmo intervalo)."""
        if carga_kw < 0 or descarga_kw < 0:
            raise ValueError("potências não podem ser negativas")
        if carga_kw > 0 and descarga_kw > 0:
            raise ValueError("a bateria não carrega e descarrega no mesmo intervalo")
        if carga_kw > self.max_carga_kw(horas) + 1e-9:
            raise ValueError("carga acima do limite da bateria")
        if descarga_kw > self.max_descarga_kw(horas) + 1e-9:
            raise ValueError("descarga acima do limite da bateria")
        energia = self.energia_kwh + carga_kw * horas * self.eficiencia - descarga_kw * horas
        self.soc = min(1.0, max(self.soc_min, energia / self.capacidade_kwh))
