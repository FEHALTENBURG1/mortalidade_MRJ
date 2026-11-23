# Painel de mortalidade e calor: Rio de Janeiro

Painel em R e Shiny (`shiny/app.R`) e página estática em Quarto (`painel_figura1.qmd`, só a Figura 1). Os métodos, as fontes e as limitações estão na aba "Métodos e fontes" do painel (`R/metodos.R`); este arquivo cobre só o que é preciso para rodar e testar.

## Estrutura

```
calcular_figura1.R   Quarto: lê o SIM e o clima, ajusta os modelos e grava saida/figura1_<pop>.json
painel_figura1.qmd   Quarto: página estática da Figura 1
R/funcoes.R          óbitos, causa, local, raça/cor, faixas, registro do SIM, clima, semanas
R/modelo_joao.R      GAM + DLNM por recorte, contrafactual, esperado semanal, curvas e mapa de limiares
R/exportar.R         JSON da figura e bloco compactado para a página
R/metodos.R          texto da aba "Métodos e fontes" (Quarto e Shiny)
R/fontes_remotas.R   Shiny: baixa o SIM e o HAAT das Releases do GitHub e mantém o cache em disco
R/servico.R          Shiny: ajuste sob demanda, cache de ajustes e pedidos assíncronos (VERSAO_AJUSTE)
shiny/               app.R, atualizar_cache.R, instalar_pacotes.R e cache/ (fora do Git)
assets/              CSS, JavaScript (figura1.js e aba_*.js), aba_*.html, Chart.js
dados_auxiliares/    cid_nomes.json, cnes_estab.csv e contorno do município
testes/              testes em R e em Python (Playwright)
```

Cada aba é um par `assets/aba_<nome>.html` e `assets/aba_<nome>.js`, registrado em `ABAS` no `shiny/app.R`. Os filtros ficam na barra lateral (`figura1_corpo.html`) e valem para todas as abas; o comparativo clona os elementos de classe `la` para o lado B (`clonarLado()` em `figura1.js`).

## Como rodar

Pacotes de R: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr` (Quarto 1.4 ou mais novo) e, no Shiny, `shiny`, `future`, `promises` e `commonmark`.

Página em Quarto:

```
Rscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv
quarto render painel_figura1.qmd
```

`--silver` é a pasta `silver` do data lake do SIM; `--haat` é o `haat_diario_municipal.csv` da Release `clima-mrj`; `--pop res` (padrão) ou `todos`; `--cores N`; `--reusar` refaz só o JSON a partir de `saida/modelos_<pop>.rds`.

App Shiny, localmente:

```
PAINEL_CACHE=pasta_do_cache Rscript -e 'shiny::runApp("shiny")'
Rscript testes/montar_cache_local.R --silver pasta/silver --haat haat_diario_municipal.csv --cache pasta_do_cache --pop res,todos
```

A segunda linha monta um cache sem rede a partir de arquivos locais.

## Cache e servidor

`shiny/atualizar_cache.R` (cron, fora das sessões) consulta a API de Releases e, se o SIM (`sim-mrj`) ou o HAAT (`clima-mrj`) mudaram, baixa os arquivos e troca o cache de forma atômica; sem versão nova, não baixa nada. Opções: `--forcar` refaz o cache inteiro; `--aquecer` e `--aquecer-cid` pré-calculam o recorte inicial (mapa de limiares e causas). O app ajusta cada recorte quando ele é pedido e guarda o resultado em `shiny/cache/ajustes/<versão dos dados>/`. Mudar `R/funcoes.R` ou `VERSAO_AJUSTE` (`R/servico.R`, hoje 4) invalida o que estava guardado.

```
cd /opt/mortalidade_MRJ && sudo -u shiny git pull
sudo Rscript painel_quarto/shiny/instalar_pacotes.R
sudo -u shiny Rscript painel_quarto/shiny/atualizar_cache.R
sudo ln -s /opt/mortalidade_MRJ/painel_quarto/shiny /srv/shiny-server/mortalidade_calor
# crontab do usuário shiny: 0 6 * * * Rscript .../shiny/atualizar_cache.R >> .../shiny/cache/cron.log 2>&1
```

O Shiny Server encerra um app que leva mais de 60 s para iniciar, por isso o download não acontece dentro da sessão: sem cache, o app dispara a atualização em segundo plano. Variáveis de ambiente, todas opcionais: `PAINEL_RAIZ`, `PAINEL_CACHE`, `PAINEL_TRABALHADORES` (modelos ao mesmo tempo, padrão 2, cerca de 300 MB cada), `PAINEL_SIM_REPOS`, `PAINEL_CLIMA_REPO` e `GITHUB_PAT` (só para subir o limite de 60 consultas por hora da API).

## Testes

```
Rscript testes/teste_funcoes.R
Rscript testes/teste_modelo.R
Rscript testes/teste_periodo.R
PAINEL_TESTE_TAR=silver_sim_mrj.tar.gz PAINEL_TESTE_HAAT=haat_diario_municipal.csv Rscript testes/teste_fontes.R
PAINEL_CACHE=pasta_do_cache PAINEL_TESTE_BASE=saida/figura1_res.json Rscript testes/teste_servico.R
python3 testes/teste_pagina.py painel_figura1.html capturas/
PAINEL_CACHE=pasta_do_cache python3 testes/teste_app.py
```

- `teste_funcoes.R`, `teste_modelo.R` e `teste_periodo.R` usam dados simulados: regras dos dados, recuperação do RR e do excesso de óbitos, curva de exposição-resposta suave e período de análise.
- `teste_fontes.R` sobe um servidor local que imita as Releases e confere primeira carga, versão igual, versão nova, tamanho errado, GitHub fora do ar e atualização simultânea. Sem as variáveis, roda só o que não precisa de dados.
- `teste_servico.R` compara cada recorte ajustado sob demanda com o do `calcular_figura1.R` e confere o cache, os códigos de erro e os pedidos assíncronos.
- `teste_pagina.py` e `teste_app.py` abrem a página estática e o app no navegador (Python com Playwright): filtros, causa do óbito, retiradas do ajuste, período, comparativo, poder estatístico e IC 95% em dica, recortes sem óbitos suficientes e dados novos.
