import pytest

from chargegrid.bateria import Bateria

H = 5 / 60


def test_descarga_respeita_potencia_e_soc_minimo():
    b = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.5)  # 8 kWh úteis
    assert b.energia_util_kwh == pytest.approx(8.0)
    assert b.max_descarga_kw(H) == 10.0
    quase_vazia = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.11)  # 0,2 kWh úteis
    assert quase_vazia.max_descarga_kw(H) == pytest.approx(0.2 / H)


def test_carga_aplica_a_perda_e_nao_passa_de_100_por_cento():
    b = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.5)
    b.aplicar(10.0, 0.0, 1.0)  # 10 kWh entram, 9 ficam
    assert b.energia_kwh == pytest.approx(19.0)
    assert b.max_carga_kw(H) == 10.0  # limitada pela potência
    assert b.max_carga_kw(1.0) == pytest.approx(1.0 / 0.9)  # limitada pelo espaço (1 kWh)
    b.aplicar(b.max_carga_kw(1.0), 0.0, 1.0)
    assert b.soc == pytest.approx(1.0)
    assert b.max_carga_kw(H) == pytest.approx(0.0)


def test_descarga_reduz_o_soc_sem_perda():
    b = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.5)
    b.aplicar(0.0, 6.0, 1.0)
    assert b.energia_kwh == pytest.approx(4.0)


def test_rejeita_carga_e_descarga_simultaneas_e_acima_do_limite():
    b = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.5)
    with pytest.raises(ValueError):
        b.aplicar(1.0, 1.0, H)
    with pytest.raises(ValueError):
        b.aplicar(11.0, 0.0, H)
    with pytest.raises(ValueError):
        b.aplicar(0.0, -1.0, H)
    vazia = Bateria(20.0, 10.0, 0.9, 0.1, soc=0.1)
    with pytest.raises(ValueError):
        vazia.aplicar(0.0, 1.0, H)


def test_parametros_invalidos_sao_rejeitados():
    with pytest.raises(ValueError):
        Bateria(0.0, 10.0)
    with pytest.raises(ValueError):
        Bateria(20.0, 10.0, soc_min=0.5, soc=0.2)
