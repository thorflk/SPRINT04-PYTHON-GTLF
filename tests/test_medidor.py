from chargegrid.medidor import MedidorModbus


def test_registradores_em_unidades_inteiras_de_w_e_wh():
    m = MedidorModbus("P1")
    m.acumular(1.5)
    regs = m.ler_registradores(7.4)
    assert regs == {"potencia_ativa_W": 7400, "energia_ativa_Wh": 1500}


def test_energia_acumulada_nunca_diminui():
    m = MedidorModbus("P2")
    anterior = 0
    for _ in range(10):
        m.acumular(0.9)
        assert m.energia_wh >= anterior
        anterior = m.energia_wh
    assert m.energia_wh == 9000
