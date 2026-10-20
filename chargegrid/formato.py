"""Formatação de números no padrão brasileiro (1.234,50) e saída de terminal em UTF-8."""

import sys


def configurar_saida_utf8() -> None:
    """Evita `UnicodeEncodeError` e acentos quebrados em consoles Windows (cp850/cp1252)."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def br(valor: float, casas: int = 2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")
