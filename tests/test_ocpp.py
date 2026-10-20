import json

import pytest

from chargegrid.ocpp import RegistroOcpp

T = "2026-09-22T18:00:00Z"


def test_start_transaction_segue_formato_call_do_ocpp_16j():
    r = RegistroOcpp()
    tid = r.start_transaction(T, "P1", "RFID-001", meter_start_wh=1200)
    tipo, uid, acao, payload = r.mensagens[0].como_call()
    assert (tipo, acao) == (2, "StartTransaction")
    assert payload == {"connectorId": 1, "idTag": "RFID-001", "meterStart": 1200, "timestamp": T}
    assert isinstance(tid, int) and isinstance(uid, str)
    assert r.mensagens[0].direcao == "CP->CS"


def test_meter_values_traz_potencia_e_energia():
    r = RegistroOcpp()
    tid = r.start_transaction(T, "P2", "RFID-002", 0)
    r.meter_values(T, "P2", potencia_w=7400, energia_wh=617)
    payload = r.mensagens[-1].payload
    assert payload["transactionId"] == tid
    amostras = payload["meterValue"][0]["sampledValue"]
    por_medida = {a["measurand"]: (a["value"], a["unit"]) for a in amostras}
    assert por_medida["Power.Active.Import"] == ("7400", "W")
    assert por_medida["Energy.Active.Import.Register"] == ("617", "Wh")


def test_set_charging_profile_vai_do_sistema_central_para_o_ponto_em_watts():
    r = RegistroOcpp()
    r.set_charging_profile(T, "P3", limite_w=5300)
    m = r.mensagens[-1]
    assert m.direcao == "CS->CP" and m.acao == "SetChargingProfile"
    periodo = m.payload["csChargingProfiles"]["chargingSchedule"]
    assert periodo["chargingRateUnit"] == "W"
    assert periodo["chargingSchedulePeriod"] == [{"startPeriod": 0, "limit": 5300}]


def test_stop_transaction_encerra_e_libera_o_id():
    r = RegistroOcpp()
    tid = r.start_transaction(T, "P4", "RFID-004", 0)
    r.stop_transaction(T, "P4", meter_stop_wh=15000, motivo="EVDisconnected")
    payload = r.mensagens[-1].payload
    assert payload["transactionId"] == tid and payload["meterStop"] == 15000
    with pytest.raises(KeyError):
        r.meter_values(T, "P4", 0, 0)


def test_ids_unicos_e_contagem_por_acao():
    r = RegistroOcpp()
    r.start_transaction(T, "P1", "A", 0)
    r.start_transaction(T, "P2", "B", 0)
    r.meter_values(T, "P1", 1, 1)
    assert len({m.unique_id for m in r.mensagens}) == 3
    assert r.contar_por_acao() == {"StartTransaction": 2, "MeterValues": 1}


def test_salvar_jsonl_grava_uma_mensagem_valida_por_linha(tmp_path):
    r = RegistroOcpp()
    r.start_transaction(T, "P1", "A", 0)
    r.meter_values(T, "P1", 7400, 617)
    caminho = tmp_path / "ocpp.jsonl"
    r.salvar_jsonl(caminho)
    linhas = caminho.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    primeira = json.loads(linhas[0])
    assert primeira["mensagem"][2] == "StartTransaction" and primeira["ponto"] == "P1"
