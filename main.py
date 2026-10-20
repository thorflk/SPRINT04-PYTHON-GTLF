"""ChargeGrid Intelligence — Sprint 4 (PCP) | FIAP x GoodWe | Grupo GTLF.

Simula 1 dia de um eletroposto comercial com usina solar, bateria, controle de demanda,
agendamento inteligente, tarifação e previsão de pico, e compara o mesmo dia em 4 estratégias
de operação. TODOS os dados são simulados. Exemplos:

    python main.py                         # execução completa (CSV, JSON, PNG, dashboard)
    python main.py --ao-vivo               # mostra a ponta intervalo a intervalo (cenário D)
    python main.py --ao-vivo --estrategia C
    python main.py --pergunta "quanto economizamos hoje?"
    python main.py --assistente            # conversa com o assistente no terminal
    streamlit run painel.py                # painel interativo no navegador
"""

import argparse
import sys
import time
from pathlib import Path

from chargegrid import config as cfg
from chargegrid.assistente import Contexto, responder
from chargegrid.estrategias import ESTRATEGIAS, PADRAO
from chargegrid.exportar import salvar_energy_flow
from chargegrid.formato import configurar_saida_utf8
from chargegrid.graficos import gerar_graficos
from chargegrid.previsao import ajustar, backtest, gerar_historico, recomendacoes
from chargegrid.relatorio import (
    formatar_dashboard,
    formatar_linha_ao_vivo,
    montar_resumo,
    salvar_saidas,
    sessoes_para_df,
    tabela_cenarios,
)
from chargegrid.simulacao import simular_dia


def _minutos(horario: str, janela: str) -> int:
    """Converte 'HH:MM' em minutos do dia, aceitando 24:00 como fim do dia."""
    try:
        horas, minutos = (int(parte) for parte in horario.split(":"))
    except ValueError as erro:
        raise ValueError(f"janela inválida: {janela!r} (use HH:MM-HH:MM)") from erro
    if not (0 <= minutos < 60 and 0 <= horas <= 24 and (horas < 24 or minutos == 0)):
        raise ValueError(f"janela inválida: {janela!r} (horário inexistente: {horario})")
    return horas * 60 + minutos


def _parse_janela(texto: str) -> tuple[int, int]:
    partes = texto.split("-")
    if len(partes) != 2:
        raise ValueError(f"janela inválida: {texto!r} (use HH:MM-HH:MM)")
    inicio, fim = (_minutos(parte, texto) for parte in partes)
    if inicio >= fim:
        raise ValueError(f"janela inválida: {texto!r} (o início deve ser menor que o fim)")
    return inicio, fim


def _erro_de_argumentos(args: argparse.Namespace) -> str | None:
    if args.dias_historico < 1:
        return "--dias-historico deve ser pelo menos 1"
    if args.velocidade < 0:
        return "--velocidade não pode ser negativa"
    return None


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="ChargeGrid Intelligence — Sprint 4 (PCP)")
    ap.add_argument("--seed", type=int, default=cfg.SEED_DEMO)
    ap.add_argument("--dias-historico", type=int, default=cfg.DIAS_HISTORICO)
    ap.add_argument("--saida", default="saida")
    ap.add_argument("--ao-vivo", action="store_true")
    ap.add_argument(
        "--estrategia",
        choices=list(ESTRATEGIAS),
        default="D",
        help="cenário mostrado no modo ao vivo (A, B, C ou D)",
    )
    ap.add_argument("--janela", default="17:00-21:00", help="HH:MM-HH:MM (só com --ao-vivo)")
    ap.add_argument("--velocidade", type=float, default=0.05, help="segundos entre intervalos")
    ap.add_argument("--sem-graficos", action="store_true")
    ap.add_argument("--sem-dashboard", action="store_true", help="não imprime o dashboard final")
    ap.add_argument(
        "--pergunta", action="append", default=[], help="pergunta ao assistente (pode repetir)"
    )
    ap.add_argument("--assistente", action="store_true", help="conversa com o assistente")
    return ap.parse_args(argv)


def _conversar(ctx: Contexto) -> None:
    print("\nAssistente ChargeGrid — pergunte sobre o dia simulado ('sair' para encerrar).")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except EOFError:
            break
        if pergunta.lower() in {"sair", "exit", "quit", ""}:
            break
        print(f"Assistente: {responder(pergunta, ctx)}")


def main(argv: list[str] | None = None) -> int:
    configurar_saida_utf8()
    args = _argumentos(argv)
    erro_args = _erro_de_argumentos(args)
    if erro_args:
        print(f"Erro: {erro_args}", file=sys.stderr)
        return 2
    callback = None
    if args.ao_vivo:
        try:
            inicio, fim = _parse_janela(args.janela)
        except ValueError as erro:
            print(f"Erro: {erro}", file=sys.stderr)
            return 2

        def callback(linha: dict, eventos: list[str]) -> None:
            if inicio <= linha["minuto"] < fim:
                print(formatar_linha_ao_vivo(linha, eventos), flush=True)
                time.sleep(args.velocidade)

        nome = ESTRATEGIAS[args.estrategia].nome
        print(
            f"Modo ao vivo: cenário {args.estrategia} ({nome}), janela {args.janela}, "
            f"seed {args.seed} (dados simulados)\n"
        )

    prev = ajustar(gerar_historico(args.dias_historico))
    demanda_prevista = prev.por_hora["media_kw"].tolist()
    resultados = {}
    for codigo, estrategia in ESTRATEGIAS.items():
        resultados[codigo] = simular_dia(
            args.seed,
            estrategia,
            PADRAO,
            ao_vivo=callback if codigo == args.estrategia else None,
            demanda_prevista_kw=demanda_prevista,
        )
    final = resultados["D"]
    resumo = montar_resumo(resultados, prev, backtest(prev, final.telemetria))
    pasta = Path(args.saida)
    salvar_saidas(resultados, resumo, pasta)
    salvar_energy_flow(final, pasta / "chargegrid_manager_energy_flow.json")
    if not args.sem_graficos:
        gerar_graficos(resultados, prev, pasta)

    textos = recomendacoes(prev, cfg.LIMITE_OPERACIONAL_KW)
    if not args.sem_dashboard:
        print(
            formatar_dashboard(
                resumo, textos, sessoes_para_df(final.sessoes), tabela_cenarios(resultados)
            )
        )
    ctx = Contexto(resultados, textos)
    for pergunta in args.pergunta:
        print(f"\nVocê: {pergunta}\nAssistente: {responder(pergunta, ctx)}")
    if args.assistente:
        _conversar(ctx)
    print(f"\nArquivos gravados em: {pasta}")  # como digitado: nunca expõe o caminho absoluto
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
