"""Mensagens no formato OCPP 1.6J (SIMULADO — sem rede, sem WebSocket).

Cada mensagem é um CALL `[2, "<uniqueId>", "<Action>", {payload}]`. Modelamos só as
requisições (`.req`); as confirmações (`.conf`) não são registradas. O log é a evidência dos
"comandos automatizados": StartTransaction/MeterValues/StopTransaction sobem do ponto
(CP->CS) e SetChargingProfile desce do controlador (CS->CP).
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MensagemOcpp:
    instante: str
    ponto: str
    direcao: str  # "CP->CS" ou "CS->CP"
    unique_id: str
    acao: str
    payload: dict

    def como_call(self) -> list:
        return [2, self.unique_id, self.acao, self.payload]

    def como_dict(self) -> dict:
        return {
            "instante": self.instante,
            "ponto": self.ponto,
            "direcao": self.direcao,
            "mensagem": self.como_call(),
        }


class RegistroOcpp:
    def __init__(self) -> None:
        self.mensagens: list[MensagemOcpp] = []
        self._sequencia = 0
        self._transacoes: dict[str, int] = {}
        self._ultimo_id_transacao = 0

    def _registrar(self, instante: str, ponto: str, direcao: str, acao: str, payload: dict) -> None:
        self._sequencia += 1
        self.mensagens.append(
            MensagemOcpp(instante, ponto, direcao, f"msg-{self._sequencia:05d}", acao, payload)
        )

    def start_transaction(self, instante: str, ponto: str, id_tag: str, meter_start_wh: int) -> int:
        self._ultimo_id_transacao += 1
        self._transacoes[ponto] = self._ultimo_id_transacao
        payload = {
            "connectorId": 1,
            "idTag": id_tag,
            "meterStart": meter_start_wh,
            "timestamp": instante,
        }
        self._registrar(instante, ponto, "CP->CS", "StartTransaction", payload)
        return self._ultimo_id_transacao

    def meter_values(self, instante: str, ponto: str, potencia_w: int, energia_wh: int) -> None:
        amostras = [
            {"value": str(potencia_w), "measurand": "Power.Active.Import", "unit": "W"},
            {"value": str(energia_wh), "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
        ]
        payload = {
            "connectorId": 1,
            "transactionId": self._transacoes[ponto],
            "meterValue": [{"timestamp": instante, "sampledValue": amostras}],
        }
        self._registrar(instante, ponto, "CP->CS", "MeterValues", payload)

    def set_charging_profile(self, instante: str, ponto: str, limite_w: int) -> None:
        perfil = {
            "chargingProfileId": self._sequencia + 1,
            "stackLevel": 0,
            "chargingProfilePurpose": "TxProfile",
            "chargingProfileKind": "Absolute",
            "chargingSchedule": {
                "chargingRateUnit": "W",
                "chargingSchedulePeriod": [{"startPeriod": 0, "limit": limite_w}],
            },
        }
        payload = {"connectorId": 1, "csChargingProfiles": perfil}
        self._registrar(instante, ponto, "CS->CP", "SetChargingProfile", payload)

    def stop_transaction(self, instante: str, ponto: str, meter_stop_wh: int, motivo: str) -> None:
        payload = {
            "transactionId": self._transacoes.pop(ponto),
            "meterStop": meter_stop_wh,
            "timestamp": instante,
            "reason": motivo,
        }
        self._registrar(instante, ponto, "CP->CS", "StopTransaction", payload)

    def contar_por_acao(self) -> dict[str, int]:
        return dict(Counter(m.acao for m in self.mensagens))

    def salvar_jsonl(self, caminho: Path | str) -> None:
        with open(caminho, "w", encoding="utf-8") as arquivo:
            for mensagem in self.mensagens:
                arquivo.write(json.dumps(mensagem.como_dict(), ensure_ascii=False) + "\n")
