import pytest

from chargegrid import config as cfg
from chargegrid.assistente import RESPOSTA_EMERGENCIA, Contexto, responder
from chargegrid.formato import br
from chargegrid.previsao import ajustar, gerar_historico, recomendacoes
from chargegrid.relatorio import metricas
from chargegrid.simulacao import simular_cenarios


@pytest.fixture(scope="module")
def ctx():
    resultados = simular_cenarios(cfg.SEED_DEMO)
    prev = ajustar(gerar_historico(4))
    return Contexto(resultados, recomendacoes(prev, cfg.LIMITE_OPERACIONAL_KW))


@pytest.mark.parametrize(
    "pergunta",
    ["Tem FUMAÇA saindo do carregador!", "vi uma faísca", "levei um choque", "cheiro de queimado"],
)
def test_emergencia_tem_resposta_fixa_antes_de_qualquer_regra(ctx, pergunta):
    assert responder(pergunta, ctx) == RESPOSTA_EMERGENCIA


def test_economia_usa_os_numeros_da_simulacao(ctx):
    m = metricas(ctx.final)
    resposta = responder("Quanto economizamos hoje?", ctx)
    assert f"R$ {br(m['custo_rede_brl'])}" in resposta
    assert "Sem gestão" in resposta


@pytest.mark.parametrize(
    ("pergunta", "trecho"),
    [
        ("quanto da energia foi solar?", "renovável"),
        ("o que a bateria fez?", "ponta"),
        ("a rede passou do limite?", "limite"),
        ("quanto CO2 evitamos?", "CO₂"),
        ("qual o melhor horário para carregar?", "Melhores horários"),
        ("compare os cenários", "4 estratégias"),
    ],
)
def test_cada_intencao_tem_resposta_propria(ctx, pergunta, trecho):
    assert trecho in responder(pergunta, ctx)


def test_sessao_por_numero_traz_os_dados_da_sessao(ctx):
    s = ctx.final.sessoes[1]
    resposta = responder("como foi a sessão 2?", ctx)
    assert s.veiculo.nome in resposta and s.ponto in resposta
    assert "carro 2" not in responder("como foi o carro 99?", ctx)
    assert "Não houve sessão 99" in responder("como foi o carro 99?", ctx)


def test_pergunta_desconhecida_explica_o_que_o_assistente_sabe(ctx):
    resposta = responder("qual a capital da França?", ctx)
    assert resposta.startswith("Não entendi") and "economizamos" in resposta
