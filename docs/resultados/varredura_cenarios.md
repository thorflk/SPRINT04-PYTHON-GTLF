# Varredura de cenários

- Dias simulados: 30 (seeds 1 a 30), cada um nas 4 estratégias
- D teve custo de rede menor que A em 30 de 30 dias, menor que B em 30 e menor que C em 24
- Violações do limite da rede no cenário D: 0 min em 30 dias (sem gestão, A: 2215 min)

A = sem gestão · B = solar + controle (Sprint 3) · C = + bateria em autoconsumo · D = solução final (bateria preditiva + agendamento por folga). “D x B (melhor/pior)” = em quantos dias D foi melhor / pior que B. Dados simulados.

| Indicador | Média A | Média B | Média C | Média D | D x A (melhor/pior) | D x B (melhor/pior) | D x C (melhor/pior) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Custo da energia da rede (R$/dia) | 128,93 | 108,45 | 88,39 | 82,84 | 30/0 | 30/0 | 24/5 |
| Energia comprada da rede (kWh/dia) | 133,0 | 107,1 | 88,1 | 89,4 | 30/0 | 30/0 | 1/23 |
| Energia da rede na ponta (kWh/dia) | 33,3 | 30,9 | 24,3 | 16,1 | 30/0 | 30/0 | 26/0 |
| Energia renovável nas recargas (%) | 0,0 | 18,5 | 33,9 | 33,0 | 30/0 | 30/0 | 0/22 |
| Pico de potência na rede (kW) | 30,44 | 23,12 | 22,73 | 23,02 | 29/1 | 5/1 | 2/3 |
| Minutos acima do limite da rede | 74 | 0 | 0 | 0 | 26/0 | 0/0 | 0/0 |
| Promessas de carga cumpridas (%) | 100,0 | 85,3 | 88,7 | 89,7 | 0/10 | 4/4 | 3/5 |
| Energia pendente na saída (kWh/dia) | 0,00 | 1,31 | 0,83 | 0,48 | 0/10 | 11/3 | 10/3 |
| Margem do operador (R$/dia) | 6,44 | 24,10 | 44,89 | 50,67 | 30/0 | 30/0 | 25/4 |
| CO₂ da energia da rede (kg/dia) | 6,13 | 4,94 | 4,06 | 4,12 | 30/0 | 30/0 | 1/22 |
