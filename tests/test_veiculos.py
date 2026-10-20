import random

from chargegrid.veiculos import CATALOGO, escolher_veiculo


def test_catalogo_tem_veiculo_capaz_de_22_kw_para_o_ponto_3():
    assert any(v.obc_kw == 22.0 for v in CATALOGO)


def test_todos_os_veiculos_tem_valores_positivos():
    assert all(v.obc_kw > 0 and v.bateria_kwh > 0 for v in CATALOGO)


def test_escolha_e_deterministica_para_a_mesma_seed():
    assert escolher_veiculo(random.Random(1)) == escolher_veiculo(random.Random(1))
