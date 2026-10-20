import pytest

from chargegrid.varredura import main, resumo_markdown, tabela_markdown, tabela_resumo, varrer


@pytest.fixture(scope="module")
def df():
    return varrer(range(1, 6))


def test_varredura_tem_os_quatro_cenarios_por_seed(df):
    assert len(df) == 5 * 4
    assert set(df["cenario"]) == {"A", "B", "C", "D"}
    assert df.groupby("seed").size().eq(4).all()


def test_com_controle_nunca_ha_violacao_do_limite(df):
    assert (df[df["cenario"] != "A"]["minutos_acima_limite"] == 0).all()


def test_solucao_final_nunca_custa_mais_que_o_eletroposto_sem_gestao(df):
    tabela = df.pivot(index="seed", columns="cenario", values="custo_rede_brl")
    assert (tabela["D"] < tabela["A"]).all()


def test_tabela_resumo_e_markdown(df):
    resumo = tabela_resumo(df)
    assert {"Média A", "Média D", "D x B (melhor/pior)"} <= set(resumo.columns)
    md = tabela_markdown(resumo)
    assert md.splitlines()[0].startswith("| Indicador |")
    assert len(md.splitlines()) == 2 + len(resumo)
    assert "Violações do limite" in resumo_markdown(df)


def test_main_grava_markdown_e_csv(tmp_path):
    destino = tmp_path / "varredura.md"
    assert main(["--n", "2", "--saida", str(destino)]) == 0
    assert "| Indicador |" in destino.read_text(encoding="utf-8")
    assert destino.with_suffix(".csv").exists()
