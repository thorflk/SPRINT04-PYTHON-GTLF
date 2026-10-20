"""Painel interativo do ChargeGrid Intelligence (Streamlit). TODOS os dados são simulados.

    streamlit run painel.py

O operador muda o dia simulado e o tamanho da usina, da bateria e da conexão com a rede, e vê
na hora o efeito em custo, energia renovável, pico e promessas de carga, nas 4 estratégias.
O assistente responde perguntas com os dados do cenário escolhido.
"""

import altair as alt
import pandas as pd
import streamlit as st

from chargegrid import config as cfg
from chargegrid.assistente import EXEMPLOS, Contexto, responder
from chargegrid.estrategias import ESTRATEGIAS, Instalacao
from chargegrid.formato import br
from chargegrid.previsao import ajustar, gerar_historico, recomendacoes
from chargegrid.relatorio import ganhos, metricas, sessoes_para_df, tabela_cenarios
from chargegrid.simulacao import simular_cenarios

CORES_FONTE = {"Solar": "#e0a800", "Bateria": "#7b4fa0", "Rede": "#3b5b92"}
CORES_CENARIO = {"A": "#7f7f7f", "B": "#3b5b92", "C": "#e08a00", "D": "#1b9e77"}

st.set_page_config(page_title="ChargeGrid Intelligence", page_icon="⚡", layout="wide")


@st.cache_resource(show_spinner=False)
def _previsao():
    return ajustar(gerar_historico(cfg.DIAS_HISTORICO))


@st.cache_resource(show_spinner="Simulando o dia nas 4 estratégias…")
def _simular(seed: int, kwp: float, bat_kwh: float, bat_kw: float, carga_kw: float):
    instalacao = Instalacao(kwp, bat_kwh, bat_kw, carga_kw)
    demanda = _previsao().por_hora["media_kw"].tolist()
    return simular_cenarios(seed, instalacao, demanda)


def _sem_latex(texto: str) -> str:
    """O Markdown do Streamlit lê "$...$" como fórmula; "R$ 1 ... R$ 2" quebraria o texto."""
    return texto.replace("$", r"\$")


def _hora(t: pd.DataFrame) -> pd.Series:
    return t["minuto"] / 60


def _faixa_ponta() -> alt.Chart:
    faixa = pd.DataFrame({"ini": [cfg.PONTA_MIN[0] / 60], "fim": [cfg.PONTA_MIN[1] / 60]})
    return alt.Chart(faixa).mark_rect(color="#f4b6b6", opacity=0.35).encode(x="ini:Q", x2="fim:Q")


def grafico_fluxo(res) -> alt.Chart:
    t = res.telemetria
    longo = pd.DataFrame(
        {
            "hora": pd.concat([_hora(t)] * 3, ignore_index=True),
            "kW": pd.concat(
                [t["solar_usada_kw"], t["bateria_kw"], t["rede_kw"]], ignore_index=True
            ),
            "fonte": ["Solar"] * len(t) + ["Bateria"] * len(t) + ["Rede"] * len(t),
            "ordem": [0] * len(t) + [1] * len(t) + [2] * len(t),
        }
    )
    escala = alt.Scale(domain=list(CORES_FONTE), range=list(CORES_FONTE.values()))
    area = (
        alt.Chart(longo)
        .mark_area(interpolate="step-after", opacity=0.85)
        .encode(
            x=alt.X("hora:Q", title="Hora do dia", scale=alt.Scale(domain=[0, 24])),
            y=alt.Y("kW:Q", stack="zero", title="Potência entregue aos carros (kW)"),
            color=alt.Color("fonte:N", scale=escala, title="Origem"),
            order="ordem:Q",
            tooltip=["hora:Q", "fonte:N", alt.Tooltip("kW:Q", format=".1f")],
        )
    )
    limite = (
        alt.Chart(pd.DataFrame({"y": [res.instalacao.limite_kw]}))
        .mark_rule(color="#c0392b", strokeDash=[6, 4], size=2)
        .encode(y="y:Q")
    )
    return (_faixa_ponta() + area + limite).properties(height=340)


def grafico_rede(resultados) -> alt.Chart:
    linhas = pd.concat(
        [
            pd.DataFrame({"hora": _hora(r.telemetria), "kW": r.telemetria["rede_kw"], "cenário": c})
            for c, r in resultados.items()
        ],
        ignore_index=True,
    )
    escala = alt.Scale(domain=list(CORES_CENARIO), range=list(CORES_CENARIO.values()))
    curvas = (
        alt.Chart(linhas)
        .mark_line(interpolate="step-after")
        .encode(
            x=alt.X("hora:Q", title="Hora do dia", scale=alt.Scale(domain=[0, 24])),
            y=alt.Y("kW:Q", title="Potência puxada da rede (kW)"),
            color=alt.Color("cenário:N", scale=escala),
            tooltip=["cenário:N", "hora:Q", alt.Tooltip("kW:Q", format=".1f")],
        )
    )
    limite = (
        alt.Chart(pd.DataFrame({"y": [next(iter(resultados.values())).instalacao.limite_kw]}))
        .mark_rule(color="#c0392b", strokeDash=[6, 4], size=2)
        .encode(y="y:Q")
    )
    return (_faixa_ponta() + curvas + limite).properties(height=320)


def grafico_soc(resultados) -> alt.Chart | None:
    partes = [
        pd.DataFrame(
            {
                "hora": _hora(r.telemetria),
                "SoC (%)": 100 * r.telemetria["soc_bateria"],
                "cenário": c,
            }
        )
        for c, r in resultados.items()
        if r.telemetria["soc_bateria"].notna().any()
    ]
    if not partes:
        return None
    escala = alt.Scale(domain=list(CORES_CENARIO), range=list(CORES_CENARIO.values()))
    curvas = (
        alt.Chart(pd.concat(partes, ignore_index=True))
        .mark_line(interpolate="step-after", size=3)
        .encode(
            x=alt.X("hora:Q", title="Hora do dia", scale=alt.Scale(domain=[0, 24])),
            y=alt.Y("SoC (%):Q", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("cenário:N", scale=escala),
        )
    )
    return (_faixa_ponta() + curvas).properties(height=300)


def grafico_barras(comp: pd.DataFrame, chave: str, titulo: str) -> alt.Chart:
    dados = comp.reset_index()[["cenario", chave]].rename(columns={chave: "valor"})
    escala = alt.Scale(domain=list(CORES_CENARIO), range=list(CORES_CENARIO.values()))
    return (
        alt.Chart(dados)
        .mark_bar()
        .encode(
            x=alt.X("cenario:N", title=None),
            y=alt.Y("valor:Q", title=None),
            color=alt.Color("cenario:N", scale=escala, legend=None),
            tooltip=["cenario:N", alt.Tooltip("valor:Q", format=",.2f")],
        )
        .properties(title=titulo, height=220)
    )


# --- barra lateral -----------------------------------------------------------------------
st.sidebar.header("⚙️ Cenário")
seed = st.sidebar.number_input("Dia simulado (seed)", 1, 999, cfg.SEED_DEMO, step=1)
kwp = st.sidebar.slider("Usina solar (kWp)", 0.0, 40.0, cfg.SOLAR_KWP, 5.0)
bat_kwh = st.sidebar.slider("Bateria (kWh)", 0.0, 60.0, cfg.BATERIA_KWH, 5.0)
bat_kw = st.sidebar.slider("Potência da bateria (kW)", 0.0, 20.0, cfg.BATERIA_KW, 2.5)
carga_kw = st.sidebar.slider(
    "Carga disponível da rede (kW)",
    20.0,
    60.0,
    cfg.CARGA_DISPONIVEL_KW,
    5.0,
    help=f"O limite operacional é {br(cfg.MARGEM_SEGURANCA)} x este valor (margem de segurança).",
)
codigo = st.sidebar.radio(
    "Estratégia em detalhe",
    list(ESTRATEGIAS),
    index=3,
    format_func=lambda c: f"{c} — {ESTRATEGIAS[c].nome}",
)
st.sidebar.caption("Todos os dados são **simulados**. Premissas no README e em `config.py`.")

resultados = _simular(int(seed), kwp, bat_kwh, bat_kw, carga_kw)
comp = tabela_cenarios(resultados)
escolhido = resultados[codigo]
m = metricas(escolhido)
base = comp.loc["A"]

# --- cabeçalho e indicadores -------------------------------------------------------------
st.title("⚡ ChargeGrid Intelligence")
st.caption(
    "Eletroposto com usina solar, bateria e carregadores GoodWe HCA G2 · FIAP x GoodWe · "
    f"Grupo GTLF · dia simulado {seed} · cenário **{codigo} — {ESTRATEGIAS[codigo].nome}** "
    "comparado ao A (sem gestão)"
)
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric(
    "Custo da rede",
    f"R$ {br(m['custo_rede_brl'])}",
    f"{br(m['custo_rede_brl'] - float(base['custo_rede_brl']))} R$",
    delta_color="inverse",
)
k2.metric(
    "Rede na ponta",
    f"{br(m['energia_rede_ponta_kwh'], 1)} kWh",
    f"{br(m['energia_rede_ponta_kwh'] - float(base['energia_rede_ponta_kwh']), 1)} kWh",
    delta_color="inverse",
)
k3.metric(
    "Energia renovável",
    f"{br(m['pct_renovavel'], 1)}%",
    f"{br(m['pct_renovavel'] - float(base['pct_renovavel']), 1)} p.p.",
)
k4.metric(
    "Pico na rede",
    f"{br(m['pico_rede_kw'], 1)} kW",
    f"{br(m['pico_rede_kw'] - float(base['pico_rede_kw']), 1)} kW",
    delta_color="inverse",
)
k5.metric(
    "Acima do limite",
    f"{m['minutos_acima_limite']} min",
    f"{m['minutos_acima_limite'] - int(base['minutos_acima_limite'])} min",
    delta_color="inverse",
)
k6.metric(
    "Promessas de carga",
    f"{m['promessas_cumpridas']}/{m['sessoes']}",
    help="Sessões que saíram com a carga prometida na chegada.",
)

abas = st.tabs(
    ["🔋 Fluxo de energia", "📊 Comparar cenários", "🚗 Sessões", "💬 Assistente", "📋 Premissas"]
)

with abas[0]:
    st.subheader("De onde veio cada kW das recargas")
    st.caption("Faixa rosa: ponta da distribuidora (17h30–20h30). Linha vermelha: limite da rede.")
    st.altair_chart(grafico_fluxo(escolhido), width="stretch")
    soc = grafico_soc({c: resultados[c] for c in ("C", "D")})
    if soc is not None:
        st.subheader("Bateria: autoconsumo (C) x despacho preditivo (D)")
        st.caption(
            "A estratégia D chega à ponta com a bateria cheia, quando o kWh da rede é mais caro."
        )
        st.altair_chart(soc, width="stretch")

with abas[1]:
    st.subheader("O mesmo dia de demanda em 4 estratégias")
    g = ganhos(comp, "A", "D")
    st.success(
        _sem_latex(
            "A solução final (D) reduz o custo da energia da rede em "
            f"**R$ {br(g['custo_rede_brl'])} ({br(g['custo_rede_pct'], 1)}%)** e a energia "
            f"comprada na ponta em **{br(g['energia_rede_ponta_pct'], 1)}%** em relação ao "
            "eletroposto sem gestão."
        )
    )
    st.altair_chart(grafico_rede(resultados), width="stretch")
    colunas = st.columns(4)
    for coluna, (chave, titulo) in zip(
        colunas,
        [
            ("custo_rede_brl", "Custo da rede (R$)"),
            ("energia_rede_ponta_kwh", "Rede na ponta (kWh)"),
            ("pct_renovavel", "Renovável (%)"),
            ("margem_brl", "Margem do operador (R$)"),
        ],
    ):
        coluna.altair_chart(grafico_barras(comp, chave, titulo), width="stretch")
    st.dataframe(comp.T.astype(str), width="stretch")

with abas[2]:
    st.subheader(f"Sessões do dia — cenário {codigo}")
    st.dataframe(sessoes_para_df(escolhido.sessoes), width="stretch", hide_index=True)

with abas[3]:
    st.subheader("Pergunte ao assistente")
    st.caption(
        "Responde sobre a solução final (D) do dia escolhido, com os dados da simulação "
        "(regras, sem LLM: nada é inventado). "
        "Exemplos: " + " · ".join(EXEMPLOS)
    )
    ctx = Contexto(resultados, recomendacoes(_previsao(), escolhido.instalacao.limite_kw))
    historico = st.session_state.setdefault("conversa", [])
    conversa = st.container()  # mensagens acima, caixa de pergunta sempre embaixo
    pergunta = st.chat_input("Ex.: quanto economizamos hoje?")
    if pergunta:
        historico += [("user", pergunta), ("assistant", responder(pergunta, ctx))]
    with conversa:
        for papel, texto in historico:
            st.chat_message(papel).markdown(_sem_latex(texto))

with abas[4]:
    st.subheader("Premissas da simulação")
    st.table(
        pd.DataFrame(
            [
                ("Pontos de recarga (GoodWe HCA G2)", "P1 7,4 · P2 11 · P3 22 · P4 7,4 kW"),
                ("Limite operacional da rede", f"{br(escolhido.instalacao.limite_kw, 1)} kW"),
                ("Usina solar", f"{br(kwp, 0)} kWp, perdas de 15%, nuvens aleatórias"),
                (
                    "Bateria",
                    f"{br(bat_kwh, 0)} kWh / {br(bat_kw, 1)} kW, 90% de eficiência, SoC mín. 10%",
                ),
                (
                    "Custo da rede (Tarifa Branca B3, Enel SP)",
                    "ponta R$ 1,56 · interm. R$ 1,03 · fora R$ 0,69/kWh",
                ),
                ("Preço ao motorista", "R$ 0,85/kWh · R$ 1,40/kWh das 18h às 21h"),
                ("Fator de emissão do SIN (MCTI, 2025)", "0,0461 kg CO₂/kWh"),
            ],
            columns=["Parâmetro", "Valor"],
        )
    )
