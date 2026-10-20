"""Varredura de seeds: os 4 cenários em N dias diferentes, para o resultado não depender de um
dia favorável.

Uso: `python -m chargegrid.varredura --n 30 --saida docs/resultados/varredura_cenarios.md`
"""

import argparse
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from chargegrid.formato import br, configurar_saida_utf8
from chargegrid.relatorio import metricas
from chargegrid.simulacao import simular_cenarios

INDICADORES = [
    # (chave, rótulo, casas, maior_e_melhor)
    ("custo_rede_brl", "Custo da energia da rede (R$/dia)", 2, False),
    ("energia_rede_kwh", "Energia comprada da rede (kWh/dia)", 1, False),
    ("energia_rede_ponta_kwh", "Energia da rede na ponta (kWh/dia)", 1, False),
    ("pct_renovavel", "Energia renovável nas recargas (%)", 1, True),
    ("pico_rede_kw", "Pico de potência na rede (kW)", 2, False),
    ("minutos_acima_limite", "Minutos acima do limite da rede", 0, False),
    ("pct_promessas", "Promessas de carga cumpridas (%)", 1, True),
    ("energia_pendente_kwh", "Energia pendente na saída (kWh/dia)", 2, False),
    ("margem_brl", "Margem do operador (R$/dia)", 2, True),
    ("co2_rede_kg", "CO₂ da energia da rede (kg/dia)", 2, False),
]


def varrer(seeds: Iterable[int]) -> pd.DataFrame:
    linhas = []
    for seed in seeds:
        for res in simular_cenarios(seed).values():
            linhas.append({"seed": seed, **metricas(res)})
    return pd.DataFrame(linhas)


def _dias_melhor(df: pd.DataFrame, chave: str, maior_melhor: bool, de: str, para: str) -> int:
    tabela = df.pivot(index="seed", columns="cenario", values=chave)
    if maior_melhor:
        return int((tabela[para] > tabela[de] + 1e-9).sum())
    return int((tabela[para] < tabela[de] - 1e-9).sum())


def _dias_pior(df: pd.DataFrame, chave: str, maior_melhor: bool, de: str, para: str) -> int:
    return _dias_melhor(df, chave, not maior_melhor, de, para)


def tabela_resumo(df: pd.DataFrame) -> pd.DataFrame:
    medias = df.groupby("cenario")[[c for c, *_ in INDICADORES]].mean()
    linhas = []
    for chave, rotulo, casas, maior in INDICADORES:
        linha = {"Indicador": rotulo}
        for cenario in medias.index:
            linha[f"Média {cenario}"] = br(float(medias.loc[cenario, chave]), casas)
        for base in ("A", "B", "C"):
            melhor = _dias_melhor(df, chave, maior, base, "D")
            pior = _dias_pior(df, chave, maior, base, "D")
            linha[f"D x {base} (melhor/pior)"] = f"{melhor}/{pior}"
        linhas.append(linha)
    return pd.DataFrame(linhas)


def tabela_markdown(df: pd.DataFrame) -> str:
    colunas = list(df.columns)
    linhas = ["| " + " | ".join(colunas) + " |", "|---|" + "---:|" * (len(colunas) - 1)]
    for registro in df.to_dict("records"):  # mantém int como int (iterrows() viraria float)
        linhas.append("| " + " | ".join(str(registro[c]) for c in colunas) + " |")
    return "\n".join(linhas)


def resumo_markdown(df: pd.DataFrame) -> str:
    n = df["seed"].nunique()
    d = df[df["cenario"] == "D"]
    custo = {base: _dias_melhor(df, "custo_rede_brl", False, base, "D") for base in "ABC"}
    return (
        f"- Dias simulados: {n} (seeds {int(df['seed'].min())} a {int(df['seed'].max())}), "
        "cada um nas 4 estratégias\n"
        f"- D teve custo de rede menor que A em {custo['A']} de {n} dias, menor que B em "
        f"{custo['B']} e menor que C em {custo['C']}\n"
        f"- Violações do limite da rede no cenário D: {int(d['minutos_acima_limite'].sum())} min "
        f"em {n} dias (sem gestão, A: "
        f"{int(df[df['cenario'] == 'A']['minutos_acima_limite'].sum())} min)\n"
    )


def main(argv: list[str] | None = None) -> int:
    configurar_saida_utf8()
    ap = argparse.ArgumentParser(description="Varredura de seeds do ChargeGrid (4 cenários)")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--saida", default="docs/resultados/varredura_cenarios.md")
    args = ap.parse_args(argv)
    df = varrer(range(1, args.n + 1))
    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    legenda = (
        "A = sem gestão · B = solar + controle (Sprint 3) · C = + bateria em autoconsumo · "
        "D = solução final (bateria preditiva + agendamento por folga). "
        "“D x B (melhor/pior)” = em quantos dias D foi melhor / pior que B. Dados simulados."
    )
    destino.write_text(
        "# Varredura de cenários\n\n"
        + resumo_markdown(df)
        + "\n"
        + legenda
        + "\n\n"
        + tabela_markdown(tabela_resumo(df))
        + "\n",
        encoding="utf-8",
    )
    destino.with_suffix(".csv").write_text(df.to_csv(index=False), encoding="utf-8")
    print(resumo_markdown(df))
    print(tabela_resumo(df).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
