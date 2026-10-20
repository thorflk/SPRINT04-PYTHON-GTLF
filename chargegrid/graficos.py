"""Gráficos PNG do dia simulado (matplotlib, backend sem janela)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from chargegrid import config as cfg  # noqa: E402
from chargegrid.previsao import Previsao  # noqa: E402
from chargegrid.relatorio import tabela_cenarios  # noqa: E402
from chargegrid.simulacao import ResultadoDia  # noqa: E402

COR_SOLAR = "#e0a800"
COR_BATERIA = "#7b4fa0"
COR_EV = "#1b9e77"
COR_REDE = "#3b5b92"
COR_LIMITE = "#c0392b"
COR_PONTA = "#f4b6b6"
CORES_CENARIO = {"A": "#7f7f7f", "B": "#3b5b92", "C": "#e08a00", "D": "#1b9e77"}
DPI = 150
PONTA_H = (cfg.PONTA_MIN[0] / 60, cfg.PONTA_MIN[1] / 60)


def _preparar(titulo: str, subtitulo: str, figsize=(11, 5)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(f"{titulo}\n{subtitulo}", fontsize=12, loc="left")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 2))
    ax.set_xlabel("Hora do dia (dia simulado)")
    ax.grid(alpha=0.25)
    ax.axvspan(*PONTA_H, color=COR_PONTA, alpha=0.35, label="Ponta da distribuidora (17h30–20h30)")
    return fig, ax


def _salvar(fig, ax, caminho: Path, loc: str = "upper left") -> None:
    ax.legend(loc=loc, fontsize=9, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(caminho, dpi=DPI)
    plt.close(fig)


def grafico_fluxo_energia(res: ResultadoDia, caminho: Path) -> None:
    t = res.telemetria
    x = t["minuto"] / 60
    fig, ax = _preparar(
        "Fluxo de energia das recargas — solução final (D)",
        f"de onde veio cada kW: solar → bateria → rede · seed {res.seed} — dados simulados",
    )
    ax.stackplot(
        x,
        t["solar_usada_kw"],
        t["bateria_kw"],
        t["rede_kw"],
        colors=[COR_SOLAR, COR_BATERIA, COR_REDE],
        alpha=0.8,
        step="post",
        labels=["Solar direto nos carros", "Bateria → carros", "Rede → carros"],
    )
    ax.step(x, t["solar_kw"], where="post", color="#8a6d00", lw=1.2, ls=":", label="Geração solar")
    ax.axhline(
        res.instalacao.limite_kw,
        color=COR_LIMITE,
        ls="--",
        lw=1.6,
        label=f"Limite da rede ({res.instalacao.limite_kw:.0f} kW)",
    )
    ax.set_ylabel("Potência (kW)")
    _salvar(fig, ax, caminho)


def grafico_origem_energia(res: ResultadoDia, caminho: Path) -> None:
    t = res.telemetria.assign(hora=res.telemetria["minuto"] // 60)
    h = cfg.PASSO_MIN / 60
    por_hora = (
        t.groupby("hora")[["solar_usada_kw", "bateria_kw", "rede_kw"]]
        .sum()
        .mul(h)
        .reindex(range(24), fill_value=0.0)
    )
    fig, ax = _preparar(
        "Origem da energia entregue, por hora (D)", "a bateria leva o sol para a ponta"
    )
    base = 0
    for coluna, cor, rotulo in (
        ("solar_usada_kw", COR_SOLAR, "Solar"),
        ("bateria_kw", COR_BATERIA, "Bateria"),
        ("rede_kw", COR_REDE, "Rede"),
    ):
        ax.bar(
            por_hora.index + 0.5, por_hora[coluna], width=0.8, bottom=base, color=cor, label=rotulo
        )
        base = base + por_hora[coluna]
    ax.set_ylabel("Energia (kWh por hora)")
    _salvar(fig, ax, caminho)


def grafico_solicitada_vs_alocada(res: ResultadoDia, caminho: Path) -> None:
    t = res.telemetria
    x = t["minuto"] / 60
    fig, ax = _preparar(
        "Agendamento inteligente: potência solicitada x alocada (D)",
        "piso garantido a cada carro; o resto vai para quem sai mais cedo; adia na ponta",
    )
    ax.step(x, t["desejada_kw"], where="post", color=COR_LIMITE, lw=1.6, label="Solicitada")
    ax.step(x, t["alocada_kw"], where="post", color=COR_EV, lw=2, label="Alocada")
    ax.step(
        x,
        t["teto_kw"],
        where="post",
        color="#555555",
        lw=1,
        ls=":",
        label="Teto (rede + solar + bateria)",
    )
    ax.fill_between(
        x,
        t["alocada_kw"],
        t["desejada_kw"],
        where=t["em_corte"].to_numpy(),
        step="post",
        color=COR_LIMITE,
        alpha=0.3,
        label="Potência reduzida ou adiada",
    )
    ax.set_ylabel("Potência total dos EVs (kW)")
    _salvar(fig, ax, caminho)


def grafico_previsao(res: ResultadoDia, prev: Previsao, caminho: Path) -> None:
    ph = prev.por_hora
    real = (
        res.telemetria.assign(hora=res.telemetria["minuto"] // 60)
        .groupby("hora")["desejada_kw"]
        .mean()
        .reindex(range(24), fill_value=0.0)
    )
    centro = ph["hora"] + 0.5
    ini, fim, _ = prev.janela_pico
    fig, ax = _preparar(
        "Previsão de demanda por hora (média histórica) x dia simulado",
        "estatística simples, não aprendizado de máquina; alimenta o despacho da bateria",
    )
    ax.fill_between(
        centro,
        (ph["media_kw"] - ph["desvio_kw"]).clip(lower=0),
        ph["media_kw"] + ph["desvio_kw"],
        color=COR_REDE,
        alpha=0.2,
        label="Previsão ± 1 desvio",
    )
    ax.plot(centro, ph["media_kw"], color=COR_REDE, lw=2, label="Previsão (média)")
    ax.plot(
        real.index + 0.5,
        real.values,
        color=COR_EV,
        lw=2,
        marker="o",
        ms=4,
        label="Dia simulado (real)",
    )
    ax.axhline(res.instalacao.limite_kw, color=COR_LIMITE, ls="--", label="Limite da rede")
    ax.axvspan(ini, fim, color="#999999", alpha=0.15, label=f"Pico previsto {ini}h–{fim}h")
    ax.set_ylabel("Demanda desejada média (kW)")
    _salvar(fig, ax, caminho)


def grafico_bateria(resultados: dict[str, ResultadoDia], caminho: Path) -> None:
    fig, ax = _preparar(
        "Estado de carga da bateria: autoconsumo (C) x despacho preditivo (D)",
        "D chega à ponta com a bateria cheia; C gasta a energia antes, quando o kWh é barato",
    )
    for codigo in ("C", "D"):
        t = resultados[codigo].telemetria
        ax.step(
            t["minuto"] / 60,
            100 * t["soc_bateria"],
            where="post",
            lw=2.2,
            color=CORES_CENARIO[codigo],
            label=f"{codigo} — {resultados[codigo].estrategia.nome}",
        )
    ax.set_ylim(0, 105)
    ax.set_ylabel("SoC da bateria (%)")
    _salvar(fig, ax, caminho)


def grafico_rede_por_cenario(resultados: dict[str, ResultadoDia], caminho: Path) -> None:
    fig, ax = _preparar(
        "Potência puxada da rede: o mesmo dia nas 4 estratégias",
        "sem gestão (A) a rede passa do limite; com a solução final (D) a ponta fica mais leve",
    )
    for codigo, res in resultados.items():
        t = res.telemetria
        ax.step(
            t["minuto"] / 60,
            t["rede_kw"],
            where="post",
            lw=2.4 if codigo == "D" else 1.3,
            color=CORES_CENARIO[codigo],
            label=f"{codigo} — {res.estrategia.nome}",
        )
    limite = next(iter(resultados.values())).instalacao.limite_kw
    ax.axhline(limite, color=COR_LIMITE, ls="--", lw=1.6, label=f"Limite da rede ({limite:.0f} kW)")
    ax.set_ylabel("Potência da rede (kW)")
    _salvar(fig, ax, caminho)


def grafico_comparativo(resultados: dict[str, ResultadoDia], caminho: Path) -> None:
    comp = tabela_cenarios(resultados)
    paineis = [
        ("custo_rede_brl", "Custo da energia da rede (R$)"),
        ("energia_rede_ponta_kwh", "Energia da rede na ponta (kWh)"),
        ("pct_renovavel", "Energia renovável nas recargas (%)"),
        ("margem_brl", "Margem do operador (R$)"),
    ]
    fig, eixos = plt.subplots(1, 4, figsize=(14, 4.2))
    seed = next(iter(resultados.values())).seed
    fig.suptitle(
        f"Comparação de cenários — mesmo dia de demanda (seed {seed}, dados simulados)",
        fontsize=12,
        x=0.01,
        ha="left",
    )
    cores = [CORES_CENARIO[c] for c in comp.index]
    for ax, (chave, titulo) in zip(eixos, paineis):
        valores = comp[chave].astype(float)
        barras = ax.bar(comp.index, valores, color=cores)
        ax.set_title(titulo, fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        for barra_, valor in zip(barras, valores):
            ax.annotate(
                f"{valor:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."),
                (barra_.get_x() + barra_.get_width() / 2, valor),
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.margins(y=0.15)
    legenda = "   ".join(f"{c} = {comp.loc[c, 'nome']}" for c in comp.index)
    fig.text(0.01, 0.01, legenda, fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    fig.savefig(caminho, dpi=DPI)
    plt.close(fig)


def gerar_graficos(
    resultados: dict[str, ResultadoDia], prev: Previsao, pasta: Path | str
) -> list[Path]:
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    final = resultados["D"]
    graficos = [
        ("01_fluxo_energia.png", lambda c: grafico_fluxo_energia(final, c)),
        ("02_origem_energia.png", lambda c: grafico_origem_energia(final, c)),
        ("03_solicitada_vs_alocada.png", lambda c: grafico_solicitada_vs_alocada(final, c)),
        ("04_previsao_pico.png", lambda c: grafico_previsao(final, prev, c)),
        ("05_bateria_soc.png", lambda c: grafico_bateria(resultados, c)),
        ("06_comparativo_cenarios.png", lambda c: grafico_comparativo(resultados, c)),
        ("07_rede_por_cenario.png", lambda c: grafico_rede_por_cenario(resultados, c)),
    ]
    caminhos = []
    for nome, desenhar in graficos:
        caminho = pasta / nome
        desenhar(caminho)
        caminhos.append(caminho)
    return caminhos
