"""Medidor por ponto de recarga, no estilo dos registradores MODBUS.

SIMULADO: não há comunicação MODBUS real; o objeto expõe os mesmos dois registradores
(potência ativa em W e energia acumulada em Wh, ambos inteiros) que um medidor de energia
devolveria a uma leitura de holding registers.
"""


class MedidorModbus:
    def __init__(self, ponto: str) -> None:
        self.ponto = ponto
        self._energia_wh = 0.0

    def acumular(self, energia_kwh: float) -> None:
        self._energia_wh += energia_kwh * 1000

    @property
    def energia_wh(self) -> int:
        return round(self._energia_wh)

    def ler_registradores(self, potencia_kw: float) -> dict[str, int]:
        return {
            "potencia_ativa_W": round(potencia_kw * 1000),
            "energia_ativa_Wh": self.energia_wh,
        }
