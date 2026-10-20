"""Assistente virtual do operador: perguntas em português respondidas com os dados do dia.

Baseado em REGRAS (palavras-chave), não em LLM: responde em milissegundos, funciona offline e
nunca inventa número, porque toda resposta é montada a partir das métricas da simulação. É a
mesma ideia de "ferramentas" do assistente do Challenge (que usa um LLM local para escrever o
texto): o dado vem sempre do sistema, não do modelo.

Segurança: relatos de emergência elétrica (fogo, fumaça, faísca, choque...) recebem uma
resposta FIXA, antes de qualquer outra regra, como no Challenge.
"""

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

from chargegrid.formato import br
from chargegrid.relatorio import ganhos, metricas, tabela_cenarios
from chargegrid.simulacao import ResultadoDia

RESPOSTA_EMERGENCIA = (
    "ATENÇÃO: isto pode ser uma emergência elétrica. Afaste as pessoas do carregador, "
    "não toque no veículo nem no cabo, acione o botão de emergência do quadro se for seguro "
    "e ligue para os Bombeiros (193). Depois avise a equipe de manutenção."
)
EXEMPLOS = [
    "quanto economizamos hoje?",
    "quanto da energia foi solar?",
    "o que a bateria fez?",
    "a rede passou do limite?",
    "quanto CO2 evitamos?",
    "como foi a sessão 3?",
    "qual o melhor horário para carregar?",
    "compare os cenários",
]


@dataclass(frozen=True)
class Contexto:
    resultados: dict[str, ResultadoDia]
    recomendacoes: list[str]

    @property
    def final(self) -> ResultadoDia:
        return self.resultados["D"]

    @property
    def comparacao(self) -> pd.DataFrame:
        return tabela_cenarios(self.resultados)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _tem(texto: str, *radicais: str) -> bool:
    return any(r in texto for r in radicais)


def _economia(ctx: Contexto) -> str:
    g = ganhos(ctx.comparacao, "A", "D")
    gb = ganhos(ctx.comparacao, "B", "D")
    m = metricas(ctx.final)
    return (
        f"Hoje a energia da rede custou R$ {br(m['custo_rede_brl'])}. Sem gestão (cenário A) "
        f"custaria R$ {br(m['custo_rede_brl'] + g['custo_rede_brl'])}: economia de "
        f"R$ {br(g['custo_rede_brl'])} ({br(g['custo_rede_pct'], 1)}%). Em relação à Sprint 3 "
        f"(cenário B), a bateria e o agendamento economizaram mais R$ {br(gb['custo_rede_brl'])}. "
        f"A margem do operador (receita menos custo da rede) foi de R$ {br(m['margem_brl'])}."
    )


def _solar(ctx: Contexto) -> str:
    m = metricas(ctx.final)
    return (
        f"{br(m['pct_renovavel'], 1)}% da energia das recargas foi renovável: "
        f"{br(m['energia_solar_kwh'], 1)} kWh direto do sol e "
        f"{br(m['energia_bateria_kwh'], 1)} kWh "
        f"da bateria, que só carrega com sol. Sobraram {br(m['solar_excedente_kwh'], 1)} kWh de "
        "geração sem uso (bateria cheia e nenhum carro carregando)."
    )


def _bateria(ctx: Contexto) -> str:
    t = ctx.final.telemetria
    m = metricas(ctx.final)
    na_ponta = t["posto"] == "ponta"
    h = 5 / 60
    entregue_ponta = float((t.loc[na_ponta, "bateria_kw"] * h).sum())
    soc_inicio_ponta = (
        float(t.loc[na_ponta, "soc_bateria_antes"].iloc[0]) if na_ponta.any() else 0.0
    )
    return (
        f"A bateria guardou {br(m['solar_para_bateria_kwh'], 1)} kWh de sol e entregou "
        f"{br(m['energia_bateria_kwh'], 1)} kWh aos carros, {br(entregue_ponta, 1)} kWh deles na "
        f"ponta (17h30–20h30), quando o kWh da rede custa R$ 1,56. Ela começou a ponta com "
        f"{soc_inicio_ponta:.0%} de carga. Regra: antes da ponta, ela só tem prioridade sobre os "
        "carros quando a previsão diz que a sobra de sol não vai enchê-la a tempo."
    )


def _pico(ctx: Contexto) -> str:
    comp = ctx.comparacao
    m = metricas(ctx.final)
    a = comp.loc["A"]
    return (
        f"Com a solução final, a rede chegou a {br(m['pico_rede_kw'], 1)} kW e ficou "
        f"{m['minutos_acima_limite']} min acima do limite de "
        f"{br(ctx.final.instalacao.limite_kw, 0)} kW. Sem gestão (A), o pico seria de "
        f"{br(float(a['pico_rede_kw']), 1)} kW, com {int(a['minutos_acima_limite'])} min acima do "
        f"limite e {int(a['minutos_acima_disponivel'])} min acima dos "
        f"{br(ctx.final.instalacao.carga_disponivel_kw, 0)} kW disponíveis (risco de desarme). "
        "Para isso, a potência de algum carro foi reduzida ou adiada por "
        f"{m['minutos_reduzidos']} min."
    )


def _co2(ctx: Contexto) -> str:
    g = ganhos(ctx.comparacao, "A", "D")
    m = metricas(ctx.final)
    return (
        f"Os {br(m['energia_entregue_kwh'], 0)} kWh recarregados evitam "
        f"{br(m['co2_evitado_vs_combustao_kg'], 1)} kg de CO₂ em relação a carros a combustão. "
        f"Além disso, comprar {br(g['energia_rede_kwh'], 1)} kWh a menos da rede evitou "
        f"{br(g['co2_rede_kg'], 2)} kg de CO₂ da geração do SIN. O número é pequeno porque a "
        "matriz brasileira já é limpa (0,0461 kg/kWh): no Brasil, o ganho maior é aliviar a rede "
        "na ponta."
    )


def _sessao(ctx: Contexto, numero: int) -> str:
    sessoes = {s.id: s for s in ctx.final.sessoes}
    if numero not in sessoes:
        return f"Não houve sessão {numero} hoje. As sessões vão de 1 a {len(sessoes)}."
    s = sessoes[numero]
    inicio = f"{s.tick_inicio * 5 // 60:02d}:{s.tick_inicio * 5 % 60:02d}"
    saida = f"{s.tick_saida * 5 // 60:02d}:{s.tick_saida * 5 % 60:02d}"
    situacao = "recebeu a carga prometida" if s.concluida else "saiu sem a carga prometida"
    motivo = ""
    if s.ticks_em_corte:
        motivo = (
            f" A potência foi reduzida ou adiada por {s.ticks_em_corte * 5} min, para respeitar o "
            "limite da rede ou fugir da ponta, sem comprometer o horário de saída."
        )
    return (
        f"Sessão {numero}: {s.veiculo.nome} no ponto {s.ponto}, das {inicio} às {saida}. "
        f"SoC de {s.soc_inicial:.0%} para {s.soc:.0%} (prometido {s.alvo:.0%}): {situacao}. "
        f"Recebeu {br(s.energia_kwh, 1)} kWh ({br(s.energia_renovavel_kwh, 1)} kWh renováveis) e "
        f"pagou R$ {br(float(s.custo))}.{motivo}"
    )


def _horario(ctx: Contexto) -> str:
    return " ".join(ctx.recomendacoes)


def _cenarios(ctx: Contexto) -> str:
    comp = ctx.comparacao
    partes = [
        f"{c} ({comp.loc[c, 'nome']}): rede R$ {br(float(comp.loc[c, 'custo_rede_brl']))}, "
        f"{br(float(comp.loc[c, 'pct_renovavel']), 0)}% renovável, "
        f"{br(float(comp.loc[c, 'pct_promessas']), 0)}% das promessas cumpridas"
        for c in comp.index
    ]
    return "O mesmo dia em 4 estratégias — " + "; ".join(partes) + "."


def _ajuda() -> str:
    return (
        "Posso responder, com os dados do dia simulado, perguntas como: "
        + "; ".join(f"“{e}”" for e in EXEMPLOS)
        + "."
    )


def responder(pergunta: str, ctx: Contexto) -> str:
    texto = _normalizar(pergunta)
    if _tem(texto, "fogo", "fumaca", "faisca", "choque", "queimad", "incendio", "explos"):
        return RESPOSTA_EMERGENCIA
    numero = re.search(r"(?:sessao|carro|veiculo|recarga)\s*(?:n[ou.]?\s*)?#?(\d+)", texto)
    if numero:
        return _sessao(ctx, int(numero.group(1)))
    regras = [
        (("cenario", "compar", "diferen", "sem o sistema", "sem gestao"), _cenarios),
        (
            ("econom", "custo", "gast", "dinheiro", "reais", "r$", "margem", "lucro", "conta"),
            _economia,
        ),
        (("bateria", "armazen", "soc", "lynx"), _bateria),
        (("co2", "carbono", "emiss", "ambient", "sustent", "polui"), _co2),
        (("pico", "limite", "demanda", "corte", "sobrecarga", "desarm"), _pico),
        (("solar", "sol ", "renovav", "fotovolt", "painel", "paineis"), _solar),
        (("horario", "hora", "quando", "melhor momento", "recomend"), _horario),
    ]
    texto_busca = texto + " "
    for radicais, resposta in regras:
        if _tem(texto_busca, *radicais):
            return resposta(ctx)
    if _tem(texto, "ajuda", "oi", "ola", "o que voce", "como funciona"):
        return _ajuda()
    return "Não entendi a pergunta. " + _ajuda()
