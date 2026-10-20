# Diagramas de arquitetura e integração — Sprint 4

Diagramas em [Mermaid](https://mermaid.js.org/), renderizados automaticamente pelo GitHub. Todos descrevem o
código **deste repositório** (os nomes de arquivo apontam onde cada bloco está implementado).

## 1. Onde este repositório se encaixa no ChargeGrid

```mermaid
flowchart LR
  subgraph CGM["ChargeGrid-Manager (Challenge) — a plataforma"]
    POR["Portal do proprietário<br/>dashboard, fluxo de energia, tarifas"]
    CLI["Portal do cliente<br/>sessão, mapa, fila, assistente"]
    API["API FastAPI + PostgreSQL"]
    POR --- API
    CLI --- API
  end
  subgraph MOT["Este repositório — o motor de otimização (Python)"]
    SIM["Simulação do eletroposto<br/>simulacao.py"]
    OTM["Despacho preditivo + agendamento<br/>despacho.py / demanda.py"]
    CEN["Cenários A-D e varredura<br/>estrategias.py / varredura.py"]
    PAI["Painel + assistente<br/>painel.py / assistente.py"]
  end
  OTM --> SIM --> CEN --> PAI
  SIM -->|"chargegrid_manager_energy_flow.json<br/>(contrato EnergyFlowResponse)"| API
  API -.->|"regras adaptadas: veículos, curva,<br/>perfil, tarifa, margem, CO₂"| SIM
```

## 2. Blocos: as três camadas da Sprint 1 na solução final

```mermaid
flowchart TB
  subgraph DIG["Camada digital (Python)"]
    PREV["Previsão de demanda<br/>previsao.py"]
    DESP["Despacho preditivo da bateria<br/>despacho.py"]
    AGE["Agendamento por folga<br/>demanda.py"]
    TAR["Tarifação: cliente + Tarifa Branca<br/>tarifacao.py"]
    REL["Relatórios, gráficos, cenários<br/>relatorio.py / graficos.py"]
    UI["Painel Streamlit + assistente<br/>painel.py / assistente.py"]
    PREV --> DESP
  end
  subgraph CON["Camada de conectividade (simulada)"]
    OCPP["OCPP 1.6J<br/>ocpp.py"]
    MOD["Medidor estilo MODBUS<br/>medidor.py"]
    EXP["Exportação no contrato do Challenge<br/>exportar.py"]
  end
  subgraph FIS["Camada física (simulada)"]
    PV["Usina solar 15 kWp<br/>solar.py"]
    BAT["Inversor híbrido + bateria GoodWe<br/>20 kWh / 10 kW — bateria.py"]
    HCA["4 carregadores HCA G2<br/>sessoes.py"]
    EV["Veículos com prazo de saída<br/>veiculos.py / sessoes.py"]
  end
  FIS --> CON --> DIG
  DIG -.->|"SetChargingProfile<br/>setpoint da bateria"| CON -.-> FIS
```

## 3. Esquema elétrico unifilar simplificado

```mermaid
flowchart LR
  REDE["Rede da concessionária<br/>30 kW disponíveis<br/>Tarifa Branca"] --> MG["Medidor geral"]
  MG --> QD["Quadro de distribuição<br/>limite operacional 24 kW"]
  PV["Módulos FV<br/>15 kWp"] --> INV["Inversor híbrido GoodWe"]
  BAT["Bateria GoodWe<br/>20 kWh / 10 kW"] <--> INV
  INV --> QD
  QD --> C1["HCA G2 - P1<br/>7,4 kW"]
  QD --> C2["HCA G2 - P2<br/>11 kW"]
  QD --> C3["HCA G2 - P3<br/>22 kW"]
  QD --> C4["HCA G2 - P4<br/>7,4 kW"]
  CTRL["Controlador Python<br/>EMS do eletroposto"]
  C1 & C2 & C3 & C4 -.->|OCPP e medição| CTRL
  INV -.->|"solar, SoC"| CTRL
  CTRL -.->|"limite por ponto"| C1 & C2 & C3 & C4
  CTRL -.->|"carga / descarga"| INV
```

O limite de 24 kW (30 kW × 0,80) vale para a **importação da rede**. Solar e bateria entram atrás do inversor
híbrido, no mesmo barramento; por isso o teto de potência para os carros é `limite + solar + descarga possível da
bateria`.

## 4. Um intervalo de 5 minutos (laço de `simulacao.py`)

```mermaid
flowchart TD
  A["Início do intervalo"] --> B["Saídas: StopTransaction<br/>Chegadas: StartTransaction + promessa de carga"]
  B --> C["Potência desejada por carro<br/>min(nominal, OBC, curva por SoC)"]
  C --> D["Geração solar do intervalo"]
  D --> E["Plano da bateria (previsão)<br/>quanto guardar · quanto liberar · reserva de pico"]
  E --> F["Agendamento por folga<br/>pisos → sobra por menor folga → orçamento na ponta"]
  F --> G["SetChargingProfile<br/>só para quem mudou"]
  G --> H["Energia entregue e SoC dos carros"]
  H --> I["Despacho: solar → bateria → rede<br/>(rede ≤ 24 kW)"]
  I --> J["Tarifa ao cliente + custo da rede (Tarifa Branca)"]
  J --> K["MeterValues e telemetria"]
  K --> L{"Último intervalo?"}
  L -- não --> A
  L -- sim --> M["Métricas, cenários, gráficos,<br/>exportação e assistente"]
```

## 5. Decisão do despacho preditivo da bateria (`despacho.plano_da_bateria`)

```mermaid
flowchart TD
  S["Intervalo de 5 min"] --> P{"Antes da ponta<br/>(17h30)?"}
  P -- sim --> Q["Previsão: sobra de sol até a ponta<br/>= geração esperada − demanda prevista"]
  Q --> R{"Sobra prevista enche<br/>o espaço livre da bateria?"}
  R -- não --> G["Guardar sol PRIMEIRO, a uma taxa<br/>falta ÷ horas de sol restantes<br/>(carros usam rede barata)"]
  R -- sim --> U["Carros usam o sol agora;<br/>a bateria pode até descarregar<br/>o que vai ser reposto"]
  P -- não --> V["Reserva = energia prevista<br/>acima do limite da rede"]
  V --> W["Liberar tudo acima da reserva<br/>(a ponta custa R$ 1,56/kWh)"]
  G & U & W --> X["Em qualquer caso: se a carga passar<br/>do limite, a bateria cobre o excesso"]
  X --> Y["Nunca carregar pela rede"]
```

## 6. Sequência de uma sessão de recarga

```mermaid
sequenceDiagram
  participant EV as Motorista / veículo
  participant CP as HCA G2 (ponto)
  participant CS as Controlador Python
  participant AG as Agendamento por folga
  participant EN as Despacho (solar/bateria/rede)
  EV->>CP: conecta, autoriza (RFID) e informa a hora de saída
  CP->>CS: StartTransaction
  CS-->>EV: promessa de carga (SoC até a saída)
  loop a cada 5 min
    CS->>AG: potência desejada, piso, folga
    AG-->>CS: potência alocada
    CS-->>CP: SetChargingProfile (só se mudou)
    CP->>CS: MeterValues (W e Wh)
    CS->>EN: carga total do intervalo
    EN-->>CS: origem: solar, bateria, rede
  end
  CP->>CS: StopTransaction (na hora de saída)
  CS-->>EV: recibo: kWh, parcela renovável, R$
```
