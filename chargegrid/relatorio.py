"""Consolida o dia simulado: métricas por cenário, resumo, arquivos, dashboard e linha ao vivo."""

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from chargegrid import config as cfg
from chargegrid.formato import br
from chargegrid.previsao import Previsao
from chargegrid.sessoes import Sessao
from chargegrid.simulacao import ResultadoDia
from chargegrid.tarifacao import em_reais

LARGURA = 72
H = cfg.PASSO_MIN / 60
COLUNAS_SESSOES = [
    "id",
    "ponto",
    "veiculo",
    "inicio",
    "saida",
    "permanencia_min",
    "soc_inicial",
    "soc_prometido",
    "soc_final",
    "promessa_cumprida",
    "energia_kwh",
    "energia_renovavel_kwh",
    "energia_pico_kwh",
    "custo_brl",
    "minutos_reduzidos",
]


def _hhmm(tick: int) -> str:
    minuto = tick * cfg.PASSO_MIN
    return f"{minuto // 60:02d}:{minuto % 60:02d}"


def sessoes_para_df(sessoes: list[Sessao]) -> pd.DataFrame:
    linhas = []
    for s in sessoes:
        linhas.append(
            {
                "id": s.id,
                "ponto": s.ponto,
                "veiculo": s.veiculo.nome,
                "inicio": _hhmm(s.tick_inicio),
                "saida": _hhmm(s.tick_saida),
                "permanencia_min": (s.tick_saida - s.tick_inicio) * cfg.PASSO_MIN,
                "soc_inicial": round(s.soc_inicial, 3),
                "soc_prometido": round(s.alvo, 3),
                "soc_final": round(s.soc, 3),
                "promessa_cumprida": s.concluida,
                "energia_kwh": round(s.energia_kwh, 3),
                "energia_renovavel_kwh": round(s.energia_renovavel_kwh, 3),
                "energia_pico_kwh": round(s.energia_pico_kwh, 3),
                "custo_brl": float(em_reais(s.custo)),
                "minutos_reduzidos": s.ticks_em_corte * cfg.PASSO_MIN,
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_SESSOES)


def metricas(res: ResultadoDia) -> dict:
    """Indicadores de um dia em uma estratégia. Mesmas chaves em todos os cenários."""
    t = res.telemetria
    kwh = lambda coluna: float((t[coluna] * H).sum())  # noqa: E731
    entregue = kwh("entregue_kw")
    solar = kwh("solar_usada_kw")
    bateria = kwh("bateria_kw")
    rede = kwh("rede_kw")
    receita = sum((s.custo for s in res.sessoes), Decimal("0"))
    custo_rede = Decimal(str(t["custo_rede_brl"].sum()))
    n = len(res.sessoes)
    cumpridas = sum(1 for s in res.sessoes if s.concluida)
    limite = res.instalacao.limite_kw
    return {
        "cenario": res.estrategia.codigo,
        "nome": res.estrategia.nome,
        "sessoes": n,
        "recusadas": res.recusadas,
        "promessas_cumpridas": cumpridas,
        "pct_promessas": round(100 * cumpridas / n, 1) if n else 100.0,
        "energia_entregue_kwh": round(entregue, 2),
        "energia_pendente_kwh": round(sum(s.falta_kwh for s in res.sessoes), 2),
        "energia_solar_kwh": round(solar, 2),
        "energia_bateria_kwh": round(bateria, 2),
        "solar_para_bateria_kwh": round(kwh("solar_bateria_kw"), 2),
        "solar_excedente_kwh": round(kwh("excedente_kw"), 2),
        "energia_rede_kwh": round(rede, 2),
        "energia_rede_ponta_kwh": round(float((t["rede_kw"] * H)[t["posto"] == "ponta"].sum()), 2),
        "pct_renovavel": round(100 * (solar + bateria) / entregue, 1) if entregue else 0.0,
        "pico_rede_kw": round(float(t["rede_kw"].max()), 2),
        "minutos_acima_limite": int((t["rede_kw"] > limite + 1e-9).sum() * cfg.PASSO_MIN),
        "minutos_acima_disponivel": int(
            (t["rede_kw"] > res.instalacao.carga_disponivel_kw + 1e-9).sum() * cfg.PASSO_MIN
        ),
        "minutos_reduzidos": int(t["em_corte"].sum() * cfg.PASSO_MIN),
        "custo_rede_brl": float(em_reais(custo_rede)),
        "receita_brl": float(em_reais(receita)),
        "margem_brl": float(em_reais(receita - custo_rede)),
        "co2_rede_kg": round(rede * cfg.FATOR_EMISSAO_REDE_KG_KWH, 2),
        "co2_evitado_vs_combustao_kg": round(
            entregue / cfg.CONSUMO_VEICULO_KWH_KM * cfg.EMISSAO_KG_CO2_KM, 2
        ),
        "soc_max_bateria": round(float(t["soc_bateria"].max()), 3)
        if t["soc_bateria"].notna().any()
        else None,
    }


def tabela_cenarios(resultados: dict[str, ResultadoDia]) -> pd.DataFrame:
    return pd.DataFrame([metricas(r) for r in resultados.values()]).set_index("cenario")


def ganhos(comparacao: pd.DataFrame, de: str = "A", para: str = "D") -> dict:
    """Diferenças objetivas entre dois cenários do mesmo dia (positivo = melhora)."""
    a, d = comparacao.loc[de], comparacao.loc[para]
    reducao = lambda chave: float(a[chave] - d[chave])  # noqa: E731
    pct = lambda chave: round(100 * reducao(chave) / a[chave], 1) if a[chave] else 0.0  # noqa: E731
    return {
        "custo_rede_brl": round(reducao("custo_rede_brl"), 2),
        "custo_rede_pct": pct("custo_rede_brl"),
        "energia_rede_kwh": round(reducao("energia_rede_kwh"), 2),
        "energia_rede_pct": pct("energia_rede_kwh"),
        "energia_rede_ponta_kwh": round(reducao("energia_rede_ponta_kwh"), 2),
        "energia_rede_ponta_pct": pct("energia_rede_ponta_kwh"),
        "pico_rede_kw": round(reducao("pico_rede_kw"), 2),
        "co2_rede_kg": round(reducao("co2_rede_kg"), 2),
        "margem_brl": round(float(d["margem_brl"] - a["margem_brl"]), 2),
    }


def montar_resumo(
    resultados: dict[str, ResultadoDia], prev: Previsao, bt: dict[str, float]
) -> dict:
    comparacao = tabela_cenarios(resultados)
    final = resultados["D"]
    ini, fim, media = prev.janela_pico
    return {
        "seed": final.seed,
        "aviso": "Todos os dados são simulados (ver README).",
        "solucao_final": metricas(final),
        "cenarios": {c: metricas(r) for c, r in resultados.items()},
        "ganhos_D_vs_A": ganhos(comparacao, "A", "D"),
        "ganhos_D_vs_B": ganhos(comparacao, "B", "D"),
        "mensagens_ocpp": final.ocpp.contar_por_acao(),
        "previsao_janela_pico": f"{ini}h-{fim}h",
        "previsao_media_pico_kw": round(media, 2),
        "previsao_mae_kw": bt["mae_kw"],
        "previsao_mae_baseline_kw": bt["mae_baseline_kw"],
    }


def salvar_saidas(
    resultados: dict[str, ResultadoDia], resumo: dict, pasta: Path | str
) -> list[Path]:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    final = resultados["D"]
    telemetria = pasta / "telemetria.csv"
    sessoes = pasta / "sessoes.csv"
    cenarios = pasta / "cenarios.csv"
    log = pasta / "ocpp_log.jsonl"
    resumo_json = pasta / "resumo.json"
    final.telemetria.to_csv(telemetria, index=False, float_format="%.3f")
    sessoes_para_df(final.sessoes).to_csv(sessoes, index=False)
    tabela_cenarios(resultados).to_csv(cenarios)
    final.ocpp.salvar_jsonl(log)
    resumo_json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return [telemetria, sessoes, cenarios, log, resumo_json]


def _plural(quantidade: int, palavra: str) -> str:
    return f"{quantidade} {palavra}" + ("" if quantidade == 1 else "s")


def _titulo(texto: str) -> str:
    return f"\n{'─' * 4} {texto} {'─' * (LARGURA - 6 - len(texto))}"


def tabela_cenarios_texto(comparacao: pd.DataFrame) -> str:
    itens = [
        ("Custo da rede (R$)", "custo_rede_brl", 2),
        ("Energia da rede (kWh)", "energia_rede_kwh", 1),
        ("  na ponta 17h30-20h30", "energia_rede_ponta_kwh", 1),
        ("Renovável (%)", "pct_renovavel", 1),
        ("Pico na rede (kW)", "pico_rede_kw", 1),
        ("Min. acima do limite", "minutos_acima_limite", 0),
        ("Promessas cumpridas (%)", "pct_promessas", 1),
        ("Margem do operador (R$)", "margem_brl", 2),
    ]
    cabecalho = f"  {'Indicador':<26}" + "".join(f"{c:>11}" for c in comparacao.index)
    linhas = [cabecalho]
    for rotulo, chave, casas in itens:
        valores = "".join(
            f"{br(float(comparacao.loc[c, chave]), casas):>11}" for c in comparacao.index
        )
        linhas.append(f"  {rotulo:<26}{valores}")
    return "\n".join(linhas)


def formatar_dashboard(
    resumo: dict, recomendacoes: list[str], sessoes_df: pd.DataFrame, comparacao: pd.DataFrame
) -> str:
    m = resumo["solucao_final"]
    g = resumo["ganhos_D_vs_A"]
    origem_limite = f"{br(cfg.CARGA_DISPONIVEL_KW, 0)} kW disponíveis x {br(cfg.MARGEM_SEGURANCA)}"
    colunas = [
        "id",
        "ponto",
        "veiculo",
        "inicio",
        "saida",
        "soc_prometido",
        "soc_final",
        "energia_kwh",
        "energia_renovavel_kwh",
        "custo_brl",
    ]
    legenda = " · ".join(f"{c} = {comparacao.loc[c, 'nome']}" for c in comparacao.index)
    linhas = [
        "═" * LARGURA,
        "  CHARGEGRID INTELLIGENCE — Solução final (Sprint 4)",
        f"  EV Challenge 2026 | FIAP x GoodWe | Grupo GTLF | seed {resumo['seed']}",
        "  Todos os dados são SIMULADOS (ver README).",
        "═" * LARGURA,
        _titulo("Operação (cenário D)"),
        f"  Sessões: {m['sessoes']} ({_plural(m['promessas_cumpridas'], 'promessa')} de carga "
        f"cumprida{'s' if m['promessas_cumpridas'] != 1 else ''}, "
        f"{_plural(m['recusadas'], 'recusada')} por falta de ponto)",
        f"  Limite da rede            : {br(cfg.LIMITE_OPERACIONAL_KW, 1)} kW ({origem_limite})",
        f"  Pico de importação        : {br(m['pico_rede_kw'], 1)} kW",
        f"  Tempo com potência reduzida (corte ou adiamento): {m['minutos_reduzidos']} min",
        _titulo("Energia: solar, bateria e rede"),
        f"  Energia entregue  : {br(m['energia_entregue_kwh'], 1)} kWh",
        f"  Solar direto      : {br(m['energia_solar_kwh'], 1)} kWh",
        f"  Bateria           : {br(m['energia_bateria_kwh'], 1)} kWh "
        f"(carregou {br(m['solar_para_bateria_kwh'], 1)} kWh de sol)",
        f"  Rede              : {br(m['energia_rede_kwh'], 1)} kWh "
        f"({br(m['energia_rede_ponta_kwh'], 1)} kWh na ponta)",
        f"  Renovável         : {br(m['pct_renovavel'], 1)}% da energia das recargas",
        _titulo("Comparação: o mesmo dia em 4 estratégias"),
        f"  {legenda}",
        tabela_cenarios_texto(comparacao),
        _titulo("Ganhos da solução final (D) sobre o eletroposto sem gestão (A)"),
        f"  Custo da energia da rede: -R$ {br(g['custo_rede_brl'])} "
        f"({br(g['custo_rede_pct'], 1)}%)",
        f"  Energia comprada da rede: -{br(g['energia_rede_kwh'], 1)} kWh "
        f"({br(g['energia_rede_pct'], 1)}%); na ponta: -{br(g['energia_rede_ponta_pct'], 1)}%",
        f"  Pico na rede: -{br(g['pico_rede_kw'], 1)} kW · CO₂ da rede evitado: "
        f"{br(g['co2_rede_kg'], 2)} kg · margem: +R$ {br(g['margem_brl'])}",
        f"  CO₂ evitado pelos EVs vs combustão: {br(m['co2_evitado_vs_combustao_kg'], 1)} kg",
        _titulo("IA — previsão que alimenta o despacho da bateria"),
        f"  Erro médio da previsão por hora: {br(resumo['previsao_mae_kw'], 2)} kW "
        f"(baseline constante: {br(resumo['previsao_mae_baseline_kw'], 2)} kW)",
        *[f"  • {texto}" for texto in recomendacoes],
        _titulo("Sessões do dia (cenário D)"),
        sessoes_df[colunas].to_string(index=False),
        "═" * LARGURA,
    ]
    return "\n".join(linhas)


def tabela_resultados_markdown(comparacao: pd.DataFrame) -> str:
    itens = [
        ("Energia entregue aos veículos (kWh)", "energia_entregue_kwh", 1),
        ("Promessas de carga cumpridas (%)", "pct_promessas", 1),
        ("Energia pendente na saída (kWh)", "energia_pendente_kwh", 2),
        ("Energia solar direto nos carros (kWh)", "energia_solar_kwh", 1),
        ("Energia entregue pela bateria (kWh)", "energia_bateria_kwh", 1),
        ("Energia comprada da rede (kWh)", "energia_rede_kwh", 1),
        ("… na ponta, 17h30–20h30 (kWh)", "energia_rede_ponta_kwh", 1),
        ("Energia renovável nas recargas (%)", "pct_renovavel", 1),
        ("Pico de potência na rede (kW)", "pico_rede_kw", 1),
        ("Minutos acima do limite de 24 kW", "minutos_acima_limite", 0),
        ("Minutos acima dos 30 kW disponíveis", "minutos_acima_disponivel", 0),
        ("Custo da energia da rede (R$)", "custo_rede_brl", 2),
        ("Receita das recargas (R$)", "receita_brl", 2),
        ("Margem do operador (R$)", "margem_brl", 2),
        ("CO₂ da energia da rede (kg)", "co2_rede_kg", 2),
    ]
    cenarios = list(comparacao.index)
    cabecalho = (
        "| Indicador | " + " | ".join(f"{c} — {comparacao.loc[c, 'nome']}" for c in cenarios) + " |"
    )
    linhas = [cabecalho, "|---|" + "---:|" * len(cenarios)]
    for rotulo, chave, casas in itens:
        valores = " | ".join(br(float(comparacao.loc[c, chave]), casas) for c in cenarios)
        linhas.append(f"| {rotulo} | {valores} |")
    return "\n".join(linhas)


def barra(valor: float, maximo: float, largura: int = 16) -> str:
    if maximo <= 0:
        cheios = 0
    else:
        cheios = round(largura * min(max(valor, 0.0), maximo) / maximo)
    return "[" + "█" * cheios + "░" * (largura - cheios) + "]"


def formatar_linha_ao_vivo(linha: dict, eventos: list[str]) -> str:
    posto = {"ponta": "PONTA ", "intermediario": "interm", "fora_ponta": "fora  "}[linha["posto"]]
    texto = (
        f"{linha['hora']}  sol {br(linha['solar_kw'], 1):>5} | "
        f"EVs {br(linha['entregue_kw'], 1):>5} | "
        f"rede {br(linha['rede_kw'], 1):>5}/{br(linha['limite_kw'], 0)} "
        f"{barra(linha['rede_kw'], linha['limite_kw'])} | "
    )
    soc = linha["soc_bateria"]
    if soc == soc:  # não é NaN: há bateria neste cenário
        fluxo = linha["bateria_kw"] - linha["solar_bateria_kw"]
        sinal = "+" if fluxo > 0.05 else ("-" if fluxo < -0.05 else " ")
        texto += f"bat {sinal}{br(abs(fluxo), 1):>4} kW {soc:4.0%} | "
    texto += posto
    if linha["em_corte"]:
        texto += f" | REDUZ {linha['fator_corte']:.0%}"
    for evento in eventos:
        texto += f"\n         > {evento}"
    return texto
