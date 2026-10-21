# Revisão metodológica do painel: o que foi feito e como foi conferido

Branch `shiny-etapa6-revisao`, a partir de `shiny-etapa5-cid`. Cada etapa é um commit. A revisão de origem é o documento "Revisão metodológica do painel de mortalidade e calor do Rio de Janeiro". O painel descreve um estudo ecológico de série temporal, com componente analítico, e não emite alertas operacionais.

Resultados do modelo por versão dos dados: `revisao_resultados.md`. Conferência dos denominadores, das causas e das datas: `conferencia_independente.md`.

## Itens da revisão

| Item | O que mudou | Onde | Como foi conferido |
|:--|:--|:--|:--|
| 1. Clima ausente é dado ausente | O dia sem dado de clima e os 10 dias seguintes saem do ajuste principal. Os óbitos desses dias continuam nos gráficos, com sombreado e legenda próprios. | `R/modelo_joao.R` (`motivo_fora`, `resumo_ajuste`), `figura1.js` | `teste_modelo.R`, `teste_servico.R`, `teste_app.py`, `conferir_independente.py` (dias sem clima) |
| 2. Amostra principal pela completude do SIM | Código de retiradas `011`: meses de registro não consolidado e dias sem clima saem; o período da COVID-19 fica, com termo próprio. Regras dos meses: taxa abaixo de 80% da mediana, dia sem óbito entre o primeiro e o último dia do arquivo, último mês incompleto. O código `000` guarda a especificação anterior. | `R/funcoes.R`, `R/modelo_joao.R`, `R/servico.R` | Mesmos testes; `conferir_independente.py` refaz os meses não consolidados a partir do texto das regras |
| 3. Causas externas e CID inválida | Causa externa é V01 a Y98. S00 a T98, causa ausente e código inválido têm grupos próprios. COVID-19 é B34.2 e U07; os demais B34 passam a causas naturais. Tabela de reconciliação em Métodos. | `R/funcoes.R`, `R/metodos.R` | `teste_funcoes.R`; `conferir_independente.py` refaz a classificação dos códigos brutos |
| 4. Diagnósticos e sensibilidades | Aba Diagnósticos e sensibilidades: Quadro 1 (dispersão, autocorrelação, Ljung-Box, `k.check`, graus de liberdade efetivos) e Quadro 2 (12 análises que mudam uma escolha por vez). | `R/servico.R`, `aba_diagnosticos.*` | `teste_modelo.R`, `teste_servico.R`, `teste_app.py` |
| 5. Curvatura estimada e reta imposta | Curva flexível (spline natural de 3 graus de liberdade) ao lado da reta do modelo de referência, com AIC e razão de desvios. A linha azul é rotulada como reta imposta. | `R/modelo_joao.R`, `aba_exposicao.*` | Testes do modelo com efeito linear e com patamar; `teste_app.py` |
| 6. Suporte dos contrastes acumulados | Quadro 4: dias com exposição, janelas e eventos independentes para cada nível e duração. Menos de 5 eventos independentes é extrapolação. | `R/modelo_joao.R`, `aba_exposicao.*` | Contagem por laço explícito no modelo, no serviço e no navegador |
| 7. Faixa semanal | A faixa é a "faixa aproximada de variação de 95%". "IC 95%" fica reservado ao RR. Quadro 5 com a cobertura por período e grupo de semanas, dentro e fora da amostra. | `R/modelo_joao.R`, `figura1.js` | Modelo (delta contra simulação, vazamento do período retirado), serviço, navegador |
| 8. Alcance do filtro de anos | "Período exibido". A seleção altera só o que é mostrado; o modelo é ajustado com a série completa. Os cartões trazem a etiqueta "Modelo ajustado com a série completa" ou "Período exibido". O modelo não é reestimado por janela. | `figura1.js`, `figura1_corpo.html` | `teste_app.py` (com menos anos, mudam os óbitos e as razões O/E; os dois RR e o Quadro 5 ficam iguais, sem novo pedido ao servidor) |
| 9. Gráficos e comparações | Gráficos alinhados de clima e óbitos (padrão). RR do modelo e razão O/E descritiva com etiquetas e bordas diferentes. Mapa de horas e limiar com dias e eventos em cada célula e destaque menor do máximo. Aba de causas: todas as estimativas visíveis, duas famílias fixas de testes (principal, com 15 grupos de referência, e exploratória), com q de Benjamini e Hochberg dentro de cada família. Capítulo e significância só filtram a exibição. | `figura1.js`, `aba_exposicao.*`, `aba_cid.*` | `teste_app.py` (família principal conferida contra a lista dos 15 grupos escrita em Python; q com as propriedades de Benjamini e Hochberg dentro de cada família; filtros sem efeito sobre o q) |
| 10. Texto de métodos e resultados | Textos prontos da revisão (apresentação, cartões, legenda dos níveis de calor, resultado por local e grupo). Vocabulário padronizado. Ficha junto de cada resultado (versão dos dados, população, recorte, causa, período do ajuste, exposição e defasagem, retiradas, família do modelo, ressalvas), também no CSV. Comparação entre grupos sem inferência pela sobreposição dos intervalos. Texto desatualizado removido. | `R/metodos.R`, `figura1.js`, `aba_*.js`, `painel_figura1.qmd` | `teste_app.py` (ficha em cada aba, CSV, varredura de termos antigos), `teste_pagina.py` |

## Critérios mínimos antes de publicar

| Critério | Situação |
|:--|:--|
| Reexecutar o modelo principal e registrar resultados anteriores e novos com a versão dos dados | `revisao_resultados.md`, gerado por `testes/registrar_resultados.R` |
| Testar residentes e todos; naturais e externas; as duas exposições; retirada de COVID, meses incompletos e clima ausente | Matriz de 40 ajustes em `revisao_resultados.md`; os testes do serviço e do navegador exercitam as causas e as retiradas |
| Conferir denominadores, CID e datas por tabelas independentes dos gráficos | `conferencia_independente.md`, gerado por `testes/conferir_independente.py` (Python, direto do Parquet do SIM e do CSV do clima) |
| Verificar se a seleção de anos altera só a exibição | Altera só a exibição: o `teste_app.py` confere que os dois RR e o Quadro 5 não mudam e que os óbitos e as razões O/E mudam |
| Registrar as limitações que permanecem | Abaixo e na seção Limitações do Métodos |

## O que a revisão encontrou nos dados (versão de dados e3)

Os números abaixo vêm do cache de desenvolvimento (SIM atualizado em 13/10/2026, clima em 19/10/2026, série de 01/01/2006 a 26/08/2026). Refaça a leitura quando o servidor tiver a versão nova.

- Conferência independente: as 87 séries diárias dos recortes elegíveis, os totais semanais, os grupos de causa, os dias sem registro, os meses não consolidados, os dias sem clima, o Nível de Calor estimado e a lista de causas da aba Causas específicas (quatro opções de causa) coincidem com o que o painel mostra.
- Resíduos do modelo principal: autocorrelação de primeira ordem de 0,28 e Ljung-Box com p < 0,001. Os intervalos dos RR provavelmente são estreitos demais.
- As 12 análises de sensibilidade mudam o log-RR em menos de 20% em relação ao ajuste principal.
- A curva flexível é sustentada pelos dados (p ≈ 2,5e-6; AIC 24 menor). A reta imposta superestima o RR para 8 h por dia (1,16 contra 1,13) e subestima o de 4 h (1,07 contra 1,10).
- Suporte: 8 h por dia mantidas por 11 dias aparece em 2 janelas e 1 evento independente. HAAT de 20 °C·h por 11 dias não aparece em nenhuma janela.
- O RR do HAAT depende de manter ou retirar os meses não consolidados (1,14 no ajuste anterior e 1,09 no principal, para 5 °C·h em residentes).
- Os demais B34 que não são COVID-19 passaram a causas naturais (59 óbitos em residentes e 79 em todos).
- Faixa semanal: dentro da amostra, cobre 95,4% das demais semanas; nas semanas de calor, 76,9% ficam dentro da faixa e 23,1% acima. Fora da amostra, as demais semanas ficam em 74,0%, com 17,8% em 2006 a 2010 (extrapolação) e 87,6% de 2023 em diante. A incerteza dos coeficientes alarga a faixa em mediana 0,6%.

## Limitações que permanecem

- A exposição é uma série municipal agregada, calculada com a média das estações.
- A rede de estações mudou ao longo da série, e o painel não ajusta essa mudança.
- O confundimento residual não está excluído. Há autocorrelação residual (Quadro 1 da aba Diagnósticos), então os intervalos dos RR podem ser estreitos demais.
- O estudo é ecológico. O RR descreve associação em dados agregados.
- O local do óbito não é a residência, e não há teste de interação entre grupos.
- A janela de defasagem de 0 a 10 dias é decisão de modelagem. O protocolo municipal trabalha com 3 dias.
- O modelo não é reestimado por período exibido. Os RR e as curvas são sempre os do modelo ajustado com a série completa.

## Publicação

- A branch muda as regras de `R/funcoes.R` (causas, clima ausente, meses não consolidados), o que invalida o cache de dados. No primeiro deploy rode `Rscript shiny/atualizar_cache.R --forcar`. `VERSAO_AJUSTE` está em 4 desde a etapa 5, então os ajustes antigos em disco são refeitos sob demanda.
- A aba de causas calcula cerca de 98 modelos na primeira visita a cada recorte (3 a 10 segundos cada). `shiny/atualizar_cache.R --aquecer` calcula de antemão o recorte inicial.
- A página estática precisa de `painel_figura1.qmd` renderizado com Quarto. O `.qmd` agora carrega `R/funcoes.R`, que o texto de Métodos exige.
