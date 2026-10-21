# Revisão metodológica: resultados do modelo principal por versão dos dados

Gerado por `testes/registrar_resultados.R`. Estudo ecológico de série temporal, com componente analítico. Os RR são da contagem diária de óbitos, acumulados em 0 a 10 dias, para a exposição mantida em todos os 11 dias em comparação com a ausência dessa exposição no mesmo intervalo, com IC 95% a partir da matriz de covariância dos coeficientes. Não são alertas operacionais.

## Versão dos dados

| População | Chave | SIM atualizado em | Clima atualizado em | Dados gerados em | Série | Óbitos por causas naturais | Dias |
|:--|:--|:--|:--|:--|:--|--:|--:|
| residentes no Rio com óbito ocorrido no município | e3 | 2026-10-13T20:50:39Z | 2026-10-19T12:18:53Z | 2026-10-20 22:18 | 2006-01-01 a 2026-08-26 | 986.757 | 7.543 |
| todos os óbitos ocorridos no município, residentes ou não | e3 | 2026-10-13T20:50:39Z | 2026-10-19T12:18:53Z | 2026-10-20 22:18 | 2006-01-01 a 2026-08-26 | 1.155.239 | 7.543 |

Versão do formato dos ajustes (`VERSAO_AJUSTE`): 4. Defasagem de 0 a 10 dias (decisão de modelagem do painel; o protocolo municipal trabalha com 3 dias). Spline do tempo com k = 20.

## Resultado anterior e novo

Anterior: nada retirado do ajuste e dias sem dado de clima contados como dias sem calor. Novo: ajuste principal, sem os meses de registro não consolidado e sem os dias sem clima (e os 10 seguintes). A variação é a diferença relativa do log-RR.

| População | Causa | Medida de calor | Nível | RR anterior (IC 95%) | RR novo (IC 95%) | Variação do log-RR | Família anterior | Família nova |
|:--|:--|:--|:--|:--|:--|--:|:--|:--|
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | 4 h | 1,06 (1,05 a 1,07) | 1,07 (1,06 a 1,08) | +20% | binomial negativa | binomial negativa |
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | 8 h | 1,13 (1,11 a 1,15) | 1,16 (1,13 a 1,18) | +20% | binomial negativa | binomial negativa |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | 5 °C·h | 1,14 (1,10 a 1,18) | 1,09 (1,06 a 1,11) | −37% | binomial negativa | binomial negativa |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | 20 °C·h | 1,16 (1,09 a 1,24) | 1,13 (1,08 a 1,18) | −20% | binomial negativa | binomial negativa |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | 4 h | 1,05 (1,03 a 1,08) | 1,05 (1,02 a 1,08) | −2% | binomial negativa | binomial negativa |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | 8 h | 1,11 (1,05 a 1,17) | 1,11 (1,05 a 1,17) | −2% | binomial negativa | binomial negativa |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | 5 °C·h | 1,05 (1,01 a 1,09) | 1,04 (1,01 a 1,08) | −17% | binomial negativa | binomial negativa |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | 20 °C·h | 1,13 (1,06 a 1,22) | 1,12 (1,04 a 1,20) | −10% | binomial negativa | binomial negativa |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | 4 h | 1,06 (1,05 a 1,07) | 1,07 (1,06 a 1,08) | +19% | binomial negativa | binomial negativa |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | 8 h | 1,12 (1,10 a 1,14) | 1,14 (1,12 a 1,16) | +19% | binomial negativa | binomial negativa |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | 5 °C·h | 1,13 (1,09 a 1,16) | 1,08 (1,05 a 1,10) | −39% | binomial negativa | binomial negativa |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | 20 °C·h | 1,18 (1,11 a 1,25) | 1,13 (1,09 a 1,18) | −25% | binomial negativa | binomial negativa |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | 4 h | 1,05 (1,03 a 1,08) | 1,05 (1,02 a 1,08) | −2% | binomial negativa | binomial negativa |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | 8 h | 1,10 (1,05 a 1,16) | 1,10 (1,05 a 1,16) | −2% | binomial negativa | binomial negativa |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | 5 °C·h | 1,05 (1,01 a 1,09) | 1,04 (1,01 a 1,08) | −20% | binomial negativa | binomial negativa |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | 20 °C·h | 1,12 (1,05 a 1,20) | 1,10 (1,03 a 1,18) | −12% | binomial negativa | binomial negativa |

## Matriz de retiradas, populações, causas e medidas

Cada linha é um ajuste do recorte geral (todos os locais e todas as idades). Dias e óbitos são os do ajuste.

| População | Causa | Medida de calor | Retiradas | Dias | Óbitos | Período do ajuste | Família | RR no 1º nível (IC 95%) | RR no 2º nível (IC 95%) |
|:--|:--|:--|:--|--:|--:|:--|:--|:--|:--|
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 986.757 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 147,4) | 1,06 (1,05 a 1,07) | 1,13 (1,11 a 1,15) |
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | meses não consolidados retirados | 7.336 | 979.824 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 258,9) | 1,07 (1,06 a 1,08) | 1,15 (1,13 a 1,17) |
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | dias sem clima (e os 10 seguintes) retirados | 6.827 | 915.027 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 140,9) | 1,06 (1,05 a 1,08) | 1,13 (1,11 a 1,16) |
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 908.094 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 255,1) | 1,07 (1,06 a 1,08) | 1,16 (1,13 a 1,18) |
| residentes | causas naturais | Horas por dia com IC ≥ 36 °C | ajuste principal e período da COVID-19 retirado | 5.895 | 789.618 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 315,2) | 1,08 (1,07 a 1,09) | 1,17 (1,14 a 1,19) |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 986.757 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 155,6) | 1,14 (1,10 a 1,18) | 1,16 (1,09 a 1,24) |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados retirados | 7.336 | 979.824 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 261,7) | 1,08 (1,06 a 1,11) | 1,12 (1,08 a 1,17) |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | dias sem clima (e os 10 seguintes) retirados | 6.827 | 915.027 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 148,7) | 1,15 (1,11 a 1,19) | 1,17 (1,09 a 1,25) |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 908.094 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 257,1) | 1,09 (1,06 a 1,11) | 1,13 (1,08 a 1,18) |
| residentes | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | ajuste principal e período da COVID-19 retirado | 5.895 | 789.618 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 318,3) | 1,09 (1,06 a 1,11) | 1,15 (1,10 a 1,19) |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 90.070 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 50,5) | 1,05 (1,03 a 1,08) | 1,11 (1,05 a 1,17) |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | meses não consolidados retirados | 7.336 | 89.400 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 55,1) | 1,05 (1,03 a 1,08) | 1,11 (1,06 a 1,17) |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | dias sem clima (e os 10 seguintes) retirados | 6.827 | 81.796 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 50,6) | 1,05 (1,02 a 1,08) | 1,10 (1,04 a 1,16) |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 81.126 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 55,7) | 1,05 (1,02 a 1,08) | 1,11 (1,05 a 1,17) |
| residentes | causas externas | Horas por dia com IC ≥ 36 °C | ajuste principal e período da COVID-19 retirado | 5.895 | 71.600 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 55,6) | 1,05 (1,02 a 1,08) | 1,10 (1,04 a 1,16) |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 90.070 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 50,0) | 1,05 (1,01 a 1,09) | 1,13 (1,06 a 1,22) |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados retirados | 7.336 | 89.400 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 54,9) | 1,05 (1,01 a 1,08) | 1,13 (1,05 a 1,21) |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | dias sem clima (e os 10 seguintes) retirados | 6.827 | 81.796 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 50,1) | 1,05 (1,01 a 1,09) | 1,13 (1,05 a 1,21) |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 81.126 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 55,6) | 1,04 (1,01 a 1,08) | 1,12 (1,04 a 1,20) |
| residentes | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | ajuste principal e período da COVID-19 retirado | 5.895 | 71.600 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 55,5) | 1,03 (1,00 a 1,07) | 1,11 (1,03 a 1,19) |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 1.155.239 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 163,1) | 1,06 (1,05 a 1,07) | 1,12 (1,10 a 1,14) |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | meses não consolidados retirados | 7.336 | 1.147.235 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 300,7) | 1,07 (1,06 a 1,08) | 1,14 (1,12 a 1,16) |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | dias sem clima (e os 10 seguintes) retirados | 6.827 | 1.070.703 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 155,3) | 1,06 (1,05 a 1,07) | 1,13 (1,10 a 1,15) |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 1.062.699 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 296,0) | 1,07 (1,06 a 1,08) | 1,14 (1,12 a 1,16) |
| todos os óbitos | causas naturais | Horas por dia com IC ≥ 36 °C | ajuste principal e período da COVID-19 retirado | 5.895 | 925.902 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 365,9) | 1,07 (1,07 a 1,08) | 1,15 (1,14 a 1,18) |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 1.155.239 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 171,4) | 1,13 (1,09 a 1,16) | 1,18 (1,11 a 1,25) |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados retirados | 7.336 | 1.147.235 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 302,6) | 1,07 (1,05 a 1,10) | 1,13 (1,09 a 1,18) |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | dias sem clima (e os 10 seguintes) retirados | 6.827 | 1.070.703 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 163,2) | 1,14 (1,10 a 1,18) | 1,18 (1,11 a 1,26) |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 1.062.699 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 296,6) | 1,08 (1,05 a 1,10) | 1,13 (1,09 a 1,18) |
| todos os óbitos | causas naturais | HAAT: graus-hora de IC acima de 36 °C no dia | ajuste principal e período da COVID-19 retirado | 5.895 | 925.902 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 365,8) | 1,07 (1,05 a 1,10) | 1,15 (1,11 a 1,19) |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 108.420 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 53,9) | 1,05 (1,03 a 1,08) | 1,10 (1,05 a 1,16) |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | meses não consolidados retirados | 7.336 | 107.645 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 58,7) | 1,05 (1,03 a 1,08) | 1,10 (1,05 a 1,16) |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | dias sem clima (e os 10 seguintes) retirados | 6.827 | 98.026 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 55,2) | 1,05 (1,02 a 1,08) | 1,10 (1,05 a 1,16) |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 97.251 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 60,3) | 1,05 (1,02 a 1,08) | 1,10 (1,05 a 1,16) |
| todos os óbitos | causas externas | Horas por dia com IC ≥ 36 °C | ajuste principal e período da COVID-19 retirado | 5.895 | 86.158 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 62,6) | 1,05 (1,02 a 1,07) | 1,09 (1,04 a 1,15) |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | nada retirado; dias sem clima contados como dias sem calor (especificação anterior) | 7.416 | 108.420 | 01/01/2006 a 26/08/2026 | binomial negativa (θ = 53,8) | 1,05 (1,01 a 1,09) | 1,12 (1,05 a 1,20) |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados retirados | 7.336 | 107.645 | 01/01/2006 a 31/07/2026 | binomial negativa (θ = 58,9) | 1,04 (1,01 a 1,08) | 1,11 (1,04 a 1,19) |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | dias sem clima (e os 10 seguintes) retirados | 6.827 | 98.026 | 27/04/2007 a 26/08/2026 | binomial negativa (θ = 54,6) | 1,05 (1,01 a 1,09) | 1,12 (1,04 a 1,20) |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | meses não consolidados e dias sem clima retirados (ajuste principal) | 6.747 | 97.251 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 60,6) | 1,04 (1,01 a 1,08) | 1,10 (1,03 a 1,18) |
| todos os óbitos | causas externas | HAAT: graus-hora de IC acima de 36 °C no dia | ajuste principal e período da COVID-19 retirado | 5.895 | 86.158 | 27/04/2007 a 31/07/2026 | binomial negativa (θ = 62,3) | 1,03 (1,00 a 1,06) | 1,09 (1,03 a 1,17) |

Níveis de referência: Horas por dia com IC ≥ 36 °C: 4 h e 8 h; HAAT: graus-hora de IC acima de 36 °C no dia: 5 °C·h e 20 °C·h.

