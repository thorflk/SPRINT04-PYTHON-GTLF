import random

import pytest

from chargegrid.demanda import Pedido, alocar, alocar_por_folga, comandos_de_limite


def test_sem_excesso_aloca_exatamente_o_desejado():
    a = alocar({"P1": 7.4, "P2": 11.0}, solar_kw=0.0, limite_kw=24.0)
    assert a.alocadas == {"P1": 7.4, "P2": 11.0}
    assert a.fator == 1.0 and not a.em_corte


def test_excesso_aplica_fator_proporcional_e_respeita_o_teto():
    d = {"P1": 7.4, "P2": 11.0, "P3": 11.0, "P4": 7.4}  # 36,8 kW > 24 kW
    a = alocar(d, solar_kw=0.0, limite_kw=24.0)
    assert a.em_corte
    assert a.fator == pytest.approx(24.0 / 36.8)
    assert a.alocada_total_kw <= 24.0 + 1e-9
    assert a.alocadas["P2"] / a.alocadas["P1"] == pytest.approx(11.0 / 7.4, abs=1e-3)


def test_solar_amplia_o_teto_e_evita_o_corte():
    d = {"P1": 7.4, "P2": 11.0, "P3": 11.0}  # 29,4 kW
    assert alocar(d, 0.0, 24.0).em_corte
    com_sol = alocar(d, 6.0, 24.0)  # teto 30 kW
    assert not com_sol.em_corte and com_sol.teto_kw == pytest.approx(30.0)


def test_solar_negativo_e_tratado_como_zero():
    assert alocar({"P1": 5.0}, -3.0, 24.0).teto_kw == pytest.approx(24.0)


def test_sem_sessoes_ativas_nao_ha_corte():
    a = alocar({}, 5.0, 24.0)
    assert a.alocadas == {} and a.fator == 1.0 and not a.em_corte


def test_propriedade_alocada_nunca_excede_desejada_nem_o_teto():
    rng = random.Random(0)
    for _ in range(300):
        d = {f"P{i}": rng.uniform(0.5, 22.0) for i in range(rng.randint(1, 4))}
        solar = rng.uniform(0, 13)
        a = alocar(d, solar, 24.0)
        assert a.alocada_total_kw <= 24.0 + solar + 1e-9
        assert all(a.alocadas[p] <= d[p] + 1e-12 for p in d)


NOMINAIS = {"P1": 7.4, "P2": 11.0}


def test_comando_e_emitido_quando_ha_corte_e_nao_repete_sem_mudanca():
    estado = {}
    cmds = comandos_de_limite(estado, {"P1": 7.4}, {"P1": 5.0}, NOMINAIS)
    assert cmds == [("P1", 5.0)]
    assert comandos_de_limite(estado, {"P1": 7.4}, {"P1": 5.01}, NOMINAIS) == []
    assert comandos_de_limite(estado, {"P1": 7.4}, {"P1": 4.5}, NOMINAIS) == [("P1", 4.5)]


def test_comando_de_liberacao_volta_ao_nominal_quando_o_corte_termina():
    estado = {"P1": 5.0}
    cmds = comandos_de_limite(estado, {"P1": 7.4}, {"P1": 7.4}, NOMINAIS)
    assert cmds == [("P1", 7.4)]
    assert estado["P1"] is None
    assert comandos_de_limite(estado, {"P1": 7.4}, {"P1": 7.4}, NOMINAIS) == []


def test_sem_corte_e_sem_estado_anterior_nao_emite_comando():
    assert comandos_de_limite({}, {"P2": 11.0}, {"P2": 11.0}, NOMINAIS) == []


def test_folga_cabe_tudo_aloca_o_desejado():
    pedidos = {"P1": Pedido(7.4, 0.0, 2.0), "P2": Pedido(11.0, 0.0, 1.0)}
    a = alocar_por_folga(pedidos, teto_kw=24.0)
    assert a.alocadas == {"P1": 7.4, "P2": 11.0} and not a.em_corte


def test_folga_garante_pisos_e_da_a_sobra_para_quem_tem_menos_folga():
    pedidos = {
        "P1": Pedido(11.0, 2.0, 3.0),  # muita folga
        "P2": Pedido(11.0, 4.0, 0.2),  # sai logo
        "P3": Pedido(11.0, 1.0, 1.0),
    }
    a = alocar_por_folga(pedidos, teto_kw=20.0)
    assert a.alocada_total_kw == pytest.approx(20.0, abs=1e-3)
    assert a.alocadas["P2"] == pytest.approx(11.0)  # menor folga: recebe tudo
    assert a.alocadas["P3"] == pytest.approx(7.0, abs=1e-3)  # segunda menor folga
    assert a.alocadas["P1"] == pytest.approx(2.0, abs=1e-3)  # só o piso


def test_folga_com_orcamento_adia_quem_pode_esperar_mas_mantem_pisos():
    pedidos = {"P1": Pedido(7.4, 0.0, 2.0), "P2": Pedido(11.0, 3.0, 0.5)}
    a = alocar_por_folga(pedidos, teto_kw=40.0, orcamento_kw=5.0)
    assert a.alocadas["P2"] == pytest.approx(5.0)  # piso 3 + sobra 2 do orçamento
    assert a.alocadas["P1"] == 0.0  # adiado
    piso_maior = alocar_por_folga(pedidos, teto_kw=40.0, orcamento_kw=1.0)
    assert piso_maior.alocadas["P2"] == pytest.approx(3.0)  # piso acima do orçamento


def test_folga_se_nem_os_pisos_cabem_corta_proporcional_sobre_os_pisos():
    pedidos = {"P1": Pedido(11.0, 10.0, 0.0), "P2": Pedido(11.0, 11.0, 0.0)}
    a = alocar_por_folga(pedidos, teto_kw=15.0)
    assert a.alocada_total_kw <= 15.0 + 1e-9
    assert a.alocadas["P2"] == pytest.approx(11.0 * 15.0 / 21.0, abs=1e-3)


def test_propriedade_folga_nunca_excede_teto_desejada_nem_deixa_piso_de_fora():
    rng = random.Random(1)
    for _ in range(300):
        pedidos = {}
        for i in range(rng.randint(1, 4)):
            desejada = rng.uniform(0.5, 22.0)
            pedidos[f"P{i}"] = Pedido(desejada, rng.uniform(0, desejada), rng.uniform(-1, 4))
        teto = rng.uniform(5, 40)
        orcamento = rng.choice([None, rng.uniform(0, 20)])
        a = alocar_por_folga(pedidos, teto, orcamento)
        assert a.alocada_total_kw <= teto + 1e-9
        assert all(a.alocadas[p] <= pedidos[p].desejada_kw + 1e-9 for p in pedidos)
        if sum(p.piso_kw for p in pedidos.values()) <= teto:
            assert all(a.alocadas[p] >= pedidos[p].piso_kw - 1e-3 for p in pedidos)
