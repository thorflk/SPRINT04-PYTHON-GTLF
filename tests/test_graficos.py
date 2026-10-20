from chargegrid import config as cfg
from chargegrid.graficos import gerar_graficos
from chargegrid.previsao import ajustar, gerar_historico
from chargegrid.simulacao import simular_cenarios

ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


def test_gera_os_sete_png_validos(tmp_path):
    resultados = simular_cenarios(cfg.SEED_DEMO)
    prev = ajustar(gerar_historico(4))
    caminhos = gerar_graficos(resultados, prev, tmp_path)
    assert [c.name for c in caminhos] == [
        "01_fluxo_energia.png",
        "02_origem_energia.png",
        "03_solicitada_vs_alocada.png",
        "04_previsao_pico.png",
        "05_bateria_soc.png",
        "06_comparativo_cenarios.png",
        "07_rede_por_cenario.png",
    ]
    for caminho in caminhos:
        conteudo = caminho.read_bytes()
        assert conteudo.startswith(ASSINATURA_PNG) and len(conteudo) > 5_000
