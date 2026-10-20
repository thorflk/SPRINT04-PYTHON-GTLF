"""Orquestra o dia simulado: sessões -> solar -> controle -> despacho -> OCPP -> medição -> tarifa.

Um tick = `cfg.PASSO_MIN` minutos. Todas as leituras são no fim do intervalo. A estratégia
(`estrategias.py`) decide só a gestão de energia; o dia de demanda (chegadas, veículos, pontos
e saídas) é o mesmo em todos os cenários com a mesma seed.

Invariantes (verificados em `tests/test_simulacao.py`, em todas as estratégias):
  solar_carga + bateria_carga + rede == entregue;  solar_carga + solar_bateria + excedente ==
  solar;  entregue <= alocada <= desejada;  rede <= limite (exceto no cenário sem gestão);
  SoC da bateria entre o mínimo e 100%.
"""

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from chargegrid import config as cfg
from chargegrid.bateria import Bateria
from chargegrid.demanda import Alocacao, Pedido, alocar, alocar_por_folga, comandos_de_limite
from chargegrid.despacho import despachar, na_ponta, plano_da_bateria
from chargegrid.estrategias import ESTRATEGIAS, FINAL, PADRAO, Estrategia, Instalacao
from chargegrid.medidor import MedidorModbus
from chargegrid.ocpp import RegistroOcpp
from chargegrid.sessoes import Sessao, criar_sessao, gerar_chegadas
from chargegrid.solar import gerar_fatores_nuvem, potencia_solar_kw
from chargegrid.tarifacao import (
    custo_do_intervalo,
    custo_rede_do_intervalo,
    eh_pico,
    posto_tarifario,
)

FuncaoAoVivo = Callable[[dict, list[str]], None]
HORAS = cfg.PASSO_MIN / 60


@dataclass
class ResultadoDia:
    seed: int
    telemetria: pd.DataFrame
    sessoes: list[Sessao]
    ocpp: RegistroOcpp
    recusadas: int
    estrategia: Estrategia = FINAL
    instalacao: Instalacao = PADRAO


def _instante(tick: int) -> str:
    momento = cfg.DATA_SIMULADA + timedelta(minutes=tick * cfg.PASSO_MIN)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hhmm(minuto: int) -> str:
    return f"{minuto // 60:02d}:{minuto % 60:02d}"


def _alocar(
    estrategia: Estrategia,
    ativas: dict[str, Sessao],
    desejadas: dict[str, float],
    tick: int,
    teto_kw: float,
    orcamento_kw: float | None,
) -> Alocacao:
    if estrategia.controle == "nenhum":
        total = sum(desejadas.values())
        return Alocacao(total, total, 1.0, dict(desejadas))
    if estrategia.controle == "proporcional":
        return alocar(desejadas, 0.0, teto_kw)
    pedidos = {
        p: Pedido(
            desejadas[p],
            s.piso_kw(tick, cfg.PONTOS[p], cfg.MARGEM_AGENDAMENTO),
            s.folga_h(tick, cfg.PONTOS[p]),
        )
        for p, s in ativas.items()
    }
    return alocar_por_folga(pedidos, teto_kw, orcamento_kw)


def simular_dia(
    seed: int,
    estrategia: Estrategia = FINAL,
    instalacao: Instalacao = PADRAO,
    ao_vivo: FuncaoAoVivo | None = None,
    demanda_prevista_kw: list[float] | None = None,
) -> ResultadoDia:
    rng = random.Random(seed)
    nuvem = gerar_fatores_nuvem(rng)
    chegadas = gerar_chegadas(rng)
    preditiva = estrategia.bateria == "preditiva"
    if preditiva and demanda_prevista_kw is None:
        from chargegrid.previsao import demanda_prevista_padrao  # evita import circular

        demanda_prevista_kw = demanda_prevista_padrao()
    bateria = None
    if estrategia.bateria is not None and instalacao.bateria_kwh > 0:
        bateria = Bateria(instalacao.bateria_kwh, instalacao.bateria_kw)
    limite = None if estrategia.controle == "nenhum" else instalacao.limite_kw

    medidores = {ponto: MedidorModbus(ponto) for ponto in cfg.PONTOS}
    ocpp = RegistroOcpp()
    ativas: dict[str, Sessao] = {}
    ultimo_limite: dict[str, float | None] = {}
    todas: list[Sessao] = []
    linhas: list[dict] = []
    recusadas = 0
    proxima = 0

    for tick in range(cfg.TICKS_POR_DIA):
        minuto = tick * cfg.PASSO_MIN
        inicio = _instante(tick)
        fim = _instante(tick + 1)
        eventos: list[str] = []

        for ponto in [p for p, s in ativas.items() if s.tick_saida <= tick]:
            sessao = ativas.pop(ponto)
            sessao.concluida, sessao.tick_fim = sessao.atingiu_alvo, tick - 1
            ultimo_limite.pop(ponto, None)
            ocpp.stop_transaction(inicio, ponto, medidores[ponto].energia_wh, "EVDisconnected")
            eventos.append(
                f"StopTransaction {ponto} ({sessao.energia_kwh:.1f} kWh, SoC {sessao.soc:.0%})"
            )

        while proxima < len(chegadas) and chegadas[proxima].tick == tick:
            chegada = chegadas[proxima]
            proxima += 1
            livres = [p for p in chegada.preferencia if p not in ativas]
            if not livres:
                recusadas += 1
                eventos.append("Chegada recusada: todos os pontos ocupados")
                continue
            ponto = livres[0]
            sessao = criar_sessao(len(todas) + 1, ponto, chegada)
            todas.append(sessao)
            ativas[ponto] = sessao
            ocpp.start_transaction(
                inicio, ponto, f"RFID-{sessao.id:03d}", medidores[ponto].energia_wh
            )
            eventos.append(
                f"StartTransaction {ponto} ({sessao.veiculo.nome}, SoC {sessao.soc:.0%}, "
                f"sai {_hhmm(sessao.tick_saida * cfg.PASSO_MIN)})"
            )

        desejadas = {p: s.potencia_desejada_kw(cfg.PONTOS[p]) for p, s in ativas.items()}
        solar_kw = (
            potencia_solar_kw(minuto, nuvem[tick], instalacao.solar_kwp)
            if estrategia.usa_solar
            else 0.0
        )
        pode_descarregar = bateria.max_descarga_kw(HORAS) if bateria else 0.0
        guardar_kw, descarga_livre, reserva = 0.0, math.inf, 0.0
        if preditiva and bateria is not None:
            guardar_kw, descarga_livre, reserva = plano_da_bateria(
                bateria,
                minuto,
                demanda_prevista_kw,
                instalacao.limite_kw,
                instalacao.solar_kwp,
                HORAS,
            )
        orcamento = None
        if estrategia.controle == "folga" and na_ponta(minuto):
            orcamento = solar_kw + min(descarga_livre, pode_descarregar)
        teto = (limite if limite is not None else math.inf) + solar_kw + pode_descarregar
        aloc = _alocar(estrategia, ativas, desejadas, tick, teto, orcamento)
        for ponto, limite_ponto in comandos_de_limite(
            ultimo_limite, desejadas, aloc.alocadas, cfg.PONTOS
        ):
            ocpp.set_charging_profile(inicio, ponto, round(limite_ponto * 1000))
            eventos.append(f"SetChargingProfile {ponto} -> {limite_ponto:.1f} kW")

        energias = {p: s.avancar(aloc.alocadas[p]) for p, s in ativas.items()}
        entregues = {p: e / HORAS for p, e in energias.items()}
        entregue_total = sum(entregues.values())
        soc_antes = bateria.soc if bateria else math.nan
        desp = despachar(
            entregue_total,
            solar_kw,
            bateria,
            limite,
            HORAS,
            guardar_kw=guardar_kw,
            descarga_livre_kw=descarga_livre,
        )
        fracao_renovavel = desp.renovavel_kw / entregue_total if entregue_total > 0 else 0.0
        pico = eh_pico(minuto)
        custo_rede = custo_rede_do_intervalo(desp.rede_kw * HORAS, minuto)

        for ponto, sessao in ativas.items():
            energia = energias[ponto]
            medidores[ponto].acumular(energia)
            regs = medidores[ponto].ler_registradores(entregues[ponto])
            ocpp.meter_values(fim, ponto, regs["potencia_ativa_W"], regs["energia_ativa_Wh"])
            em_corte = aloc.alocadas[ponto] < desejadas[ponto] - 1e-9
            sessao.registrar(
                energia, fracao_renovavel, custo_do_intervalo(energia, minuto), pico, em_corte
            )

        linha = {
            "tick": tick,
            "hora": _hhmm(minuto),
            "minuto": minuto,
            "solar_kw": solar_kw,
            "desejada_kw": aloc.desejada_total_kw,
            "teto_kw": aloc.teto_kw if math.isfinite(aloc.teto_kw) else aloc.desejada_total_kw,
            "alocada_kw": aloc.alocada_total_kw,
            "entregue_kw": entregue_total,
            "solar_usada_kw": desp.solar_para_carga_kw,
            "solar_bateria_kw": desp.solar_para_bateria_kw,
            "bateria_kw": desp.bateria_para_carga_kw,
            "excedente_kw": desp.excedente_kw,
            "rede_kw": desp.rede_kw,
            "soc_bateria": bateria.soc if bateria else math.nan,
            "soc_bateria_antes": soc_antes,
            "reserva_pico_kwh": reserva,
            "limite_kw": instalacao.limite_kw,
            "fator_corte": aloc.fator,
            "em_corte": aloc.em_corte,
            "pontos_ativos": len(ativas),
            "em_pico": pico,
            "posto": posto_tarifario(minuto),
            "custo_rede_brl": float(custo_rede),
        }
        for ponto in cfg.PONTOS:
            linha[f"{ponto}_desejada_kw"] = desejadas.get(ponto, 0.0)
            linha[f"{ponto}_alocada_kw"] = aloc.alocadas.get(ponto, 0.0)
            linha[f"{ponto}_entregue_kw"] = entregues.get(ponto, 0.0)
        linhas.append(linha)

        if ao_vivo is not None:
            ao_vivo(linha, eventos)

    fim_do_dia = _instante(cfg.TICKS_POR_DIA)
    for ponto, sessao in ativas.items():  # o shopping fecha: todos saem à meia-noite
        sessao.concluida, sessao.tick_fim = sessao.atingiu_alvo, cfg.TICKS_POR_DIA - 1
        ocpp.stop_transaction(fim_do_dia, ponto, medidores[ponto].energia_wh, "EVDisconnected")

    return ResultadoDia(seed, pd.DataFrame(linhas), todas, ocpp, recusadas, estrategia, instalacao)


def simular_cenarios(
    seed: int,
    instalacao: Instalacao = PADRAO,
    demanda_prevista_kw: list[float] | None = None,
) -> dict[str, ResultadoDia]:
    """O mesmo dia de demanda nas quatro estratégias, na ordem A, B, C, D."""
    return {
        codigo: simular_dia(seed, estrategia, instalacao, demanda_prevista_kw=demanda_prevista_kw)
        for codigo, estrategia in ESTRATEGIAS.items()
    }
