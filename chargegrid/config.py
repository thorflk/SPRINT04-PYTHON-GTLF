"""Constantes e premissas do protótipo — única fonte de verdade.

Origem de cada valor (ver README, seção "Premissas"):
  * Sprint 2 (`main.py`): potências dos pontos, tarifas, janela de pico.
  * Challenge (ChargeGrid-Manager): margem de segurança (`dimensionamento.py`), perfil de
    chegadas (`simulador/profiles.py`), fatores de CO2 (`services/sustainability.py`).
  * Challenge, Sprint 4 SERS (`docs/sers-sprint4.md`, seção 6.5, fontes oficiais): Tarifa
    Branca B3 da Enel SP (ANEEL, REH nº 3.596/2026) e fator de emissão do SIN (MCTI/SIRENE).
  * PREMISSA DO GRUPO (não é dado real): usina solar, bateria, carga disponível de 30 kW,
    veículo de 22 kW, tempo de permanência no shopping e parâmetros do despacho preditivo.
"""

from datetime import datetime
from decimal import Decimal

# --- tempo -------------------------------------------------------------------------------
PASSO_MIN = 5
TICKS_POR_DIA = 24 * 60 // PASSO_MIN  # 288
DATA_SIMULADA = datetime(2026, 9, 22)  # terça-feira; usada só nos carimbos de tempo

# --- eletroposto -------------------------------------------------------------------------
PONTOS = {"P1": 7.4, "P2": 11.0, "P3": 22.0, "P4": 7.4}  # potência nominal (kW), Sprint 2
CARGA_DISPONIVEL_KW = 30.0  # PREMISSA DO GRUPO (seed do Challenge usa 40 kW; é configurável)
MARGEM_SEGURANCA = 0.80  # `SAFETY_MARGIN` de dimensionamento.py (Challenge)
LIMITE_OPERACIONAL_KW = CARGA_DISPONIVEL_KW * MARGEM_SEGURANCA  # 24 kW de importação da rede

# --- tarifa (Sprint 2) -------------------------------------------------------------------
TARIFA_NORMAL = Decimal("0.85")  # R$/kWh, preço ao motorista
TARIFA_PICO = Decimal("1.40")  # R$/kWh, 18h <= hora < 21h
HORA_PICO_INICIO = 18
HORA_PICO_FIM = 21

# --- custo da energia da rede para o operador: Tarifa Branca B3, Enel SP ----------------
# ANEEL, REH nº 3.596/2026, Tabela 2 (sem impostos e sem bandeira); postos da Enel SP em dias
# úteis. Valores em R$/kWh. Substitui o custo fixo de R$ 0,60/kWh (premissa) da Sprint 3.
CUSTO_REDE_PONTA = Decimal("1.55911")
CUSTO_REDE_INTERMEDIARIO = Decimal("1.03179")
CUSTO_REDE_FORA_PONTA = Decimal("0.68501")
PONTA_MIN = (17 * 60 + 30, 20 * 60 + 30)  # 17h30-20h30
INTERMEDIARIO_MIN = ((16 * 60 + 30, 17 * 60 + 30), (20 * 60 + 30, 21 * 60 + 30))

# --- usina solar (PREMISSA DO GRUPO) -----------------------------------------------------
SOLAR_KWP = 15.0
SOLAR_DERATE = 0.85  # perdas de sistema (temperatura, cabos, inversor)
SOLAR_NASCER_H = 6.0
SOLAR_POENTE_H = 18.0
PROB_NUVEM = 0.04  # chance por tick de começar um evento de nuvem

# --- armazenamento: inversor híbrido GoodWe + bateria (PREMISSA DO GRUPO) ----------------
# Mesmos valores do estabelecimento de demonstração do Challenge (20 kWh / 10 kW). São
# premissas de simulação, não a ficha técnica de um modelo específico.
BATERIA_KWH = 20.0
BATERIA_KW = 10.0  # potência máxima de carga e de descarga
BATERIA_EFICIENCIA = 0.90  # ida e volta; a perda inteira é aplicada na carga (como no Challenge)
BATERIA_SOC_MIN = 0.10  # protege a vida útil
BATERIA_SOC_INICIAL = 0.10  # o dia começa com a bateria no mínimo: nenhum kWh "de graça"

# --- despacho preditivo e agendamento inteligente (PREMISSA DO GRUPO) --------------------
# Fração da potência máxima que o agendador supõe ter no futuro ao decidir quanto pode adiar
# uma recarga (< 1 porque, no futuro, o ponto pode estar dividindo a potência com outros).
MARGEM_AGENDAMENTO = 0.6
# Fração da geração de céu limpo que o despacho espera ter, em média, no resto do dia
# (as nuvens simuladas tiram cerca de 8% da geração; 0,8 deixa folga para dias mais nublados).
FATOR_PREVISAO_SOLAR = 0.8

# --- curva de carga do veículo (curve_engine.py do Challenge) ----------------------------
SOC_INICIO_TAPER = 0.80
TAPER_FIM_FRACAO_NOMINAL = 0.10
SOC_INICIAL_MIN = 0.10
SOC_INICIAL_MAX = 0.50
ALVOS_SOC = (0.80, 0.90, 1.00)
# Tempo que o carro fica estacionado no shopping (PREMISSA DO GRUPO). O carro ocupa o ponto
# até sair, mesmo depois de carregado; o shopping fecha e todos saem até a meia-noite.
PERMANENCIA_H = (1.5, 4.5)
# Ao chegar, o motorista recebe uma PROMESSA de carga: o SoC que o carro alcançaria no tempo de
# permanência com esta fração da potência máxima (margem para dividir a rede com outros carros).
FATOR_PROMESSA = 0.85


# --- perfil de chegadas: shopping, dia útil (profiles.py do Challenge) -------------------
def _pesos_shopping() -> tuple[float, ...]:
    pesos = []
    for hora in range(24):
        if 18 <= hora < 22:
            pesos.append(6.0)
        elif 10 <= hora < 18:
            pesos.append(1.5)
        else:
            pesos.append(0.2)
    return tuple(pesos)


PESOS_CHEGADA_POR_HORA = _pesos_shopping()
SESSOES_POR_PONTO_DIA = (1, 3)

# --- sustentabilidade (sustainability.py + config.py do Challenge) -----------------------
CONSUMO_VEICULO_KWH_KM = 0.16
EMISSAO_KG_CO2_KM = 0.12
# Fator médio de emissão do SIN, 2025 (MCTI/SIRENE, inventários corporativos): 0,0461 tCO2/MWh
FATOR_EMISSAO_REDE_KG_KWH = 0.0461

# --- previsão ----------------------------------------------------------------------------
LARGURA_JANELA_PICO_H = 3
TOP_HORAS_RECOMENDADAS = 3
SOLAR_MINIMO_RECOMENDACAO_KW = 5.0

# --- reprodutibilidade -------------------------------------------------------------------
# Seed da demonstração (Sprint 4): a MENOR seed de 1 a 60 em que (1) sem gestão a rede passa
# >= 30 min do limite e chega a passar da carga disponível; (2) a Sprint 3 precisa reduzir a
# potência >= 30 min; (3) o custo da rede cai a cada etapa, A > B > C > D; (4) D cumpre ao menos
# tantas promessas de carga quanto B e C; (5) há >= 8 sessões; (6) a bateria do cenário D chega
# à ponta com >= 90%. `python -m chargegrid.varredura` mostra que os ganhos valem nas demais seeds.
SEED_DEMO = 15
SEED_HISTORICO_BASE = 1000
DIAS_HISTORICO = 14
