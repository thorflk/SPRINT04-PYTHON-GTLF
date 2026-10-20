from chargegrid.formato import br, configurar_saida_utf8


def test_configurar_saida_utf8_nao_quebra_com_fluxo_sem_reconfigure(monkeypatch):
    class FluxoSimples:  # como o stdout substituído pelo pytest: sem `.reconfigure`
        pass

    monkeypatch.setattr("sys.stdout", FluxoSimples())
    monkeypatch.setattr("sys.stderr", FluxoSimples())
    configurar_saida_utf8()  # não deve levantar exceção


def test_br_usa_virgula_decimal_e_ponto_de_milhar():
    assert br(1234.5) == "1.234,50"
    assert br(0.85) == "0,85"
    assert br(24, 0) == "24"
