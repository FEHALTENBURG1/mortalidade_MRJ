# Painel de mortalidade e calor em R e Quarto: Figura 1

Versão em R e Quarto da Figura 1 do painel (óbitos por causas naturais contra o número esperado sem calor, Rio de Janeiro). O painel em Python continua como está; esta pasta cobre só a Figura 1 e as demais abas serão migradas uma a uma.

O resultado é um arquivo HTML único (`painel_figura1.html`), sem servidor: o R ajusta os modelos, grava os resultados em JSON e o Quarto embute tudo na página. Os filtros (local do óbito, faixa etária, raça/cor, escala semanal ou diária, medida de calor, período) só escolhem entre modelos já calculados.

## O que mudou

- Modelo. Cada recorte tem um modelo do João (GAM com `mgcv` mais cross-basis do `dlnm`, defasagem de 0 a 10 dias, binomial negativa), ajustado só aos óbitos daquele recorte. O esperado é o contrafactual sem calor desse modelo. No painel anterior a linha esperada da figura semanal vinha de um modelo só de tendência e sazonalidade, o que deixava a razão observado ÷ esperado perto de 1,00 em qualquer recorte.
- Faixas etárias da UNICEF: 0-4, 5-9, 10-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79 e 80+.
- Registro não consolidado. Mesma regra do painel em Python: meses abaixo de 80% da mediana de referência ficam no ajuste e aparecem hachurados; dias sem nenhum óbito no SIM saem do ajuste.
- Duas medidas de calor. Horas por dia com índice de calor ≥ 36 °C (spline natural, 1 gl) e HAAT, os graus-hora acima de 36 °C (spline penalizado, 15 gl).

## Estrutura

```
calcular_figura1.R        driver: lê o SIM e o clima, ajusta os modelos e grava saida/figura1_<pop>.json
R/funcoes.R               óbitos (nanoparquet), causas, local, raça/cor, faixas, registro do SIM, clima, semanas
R/modelo_joao.R           GAM + DLNM por segmento, contrafactual e esperado semanal
R/exportar.R              JSON da figura e bloco compactado para a página
R/fontes_remotas.R        Shiny: baixa o SIM e o HAAT das Releases do GitHub e mantém o cache em disco
shiny/                    Shiny: atualizar_cache.R (cron), instalar_pacotes.R e a pasta cache/ (fora do Git)
painel_figura1.qmd        página (métodos em texto, números calculados em R)
assets/                   CSS, JavaScript da figura, Chart.js e markup dos filtros
dados_auxiliares/         cnes_estab.csv (tipo dos estabelecimentos)
testes/                   testes das funções, do modelo (dados simulados) e da página (Playwright)
```

## Como rodar

Pacotes de R: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr`. Quarto 1.4 ou mais novo.

```
Rscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv
quarto render painel_figura1.qmd
```

- `--silver`: pasta `silver` do data lake do SIM (`sim/ocorrencia_mrj/ano_arquivo=*/part-0.parquet`).
- `--haat`: `haat_diario_municipal.csv` do Release `clima-mrj`.
- `--pop res` (padrão, residentes que morreram no Rio) ou `--pop todos`. Para a página usar `todos`, defina `PAINEL_POP=todos` antes de `quarto render`.
- `--cores N`: processos em paralelo (no Windows roda em um só).
- `--reusar`: não reajusta; refaz só o JSON a partir de `saida/modelos_<pop>.rds`.

São cerca de 90 recortes por medida de calor; o ajuste leva alguns minutos por medida. A leitura do SIM leva cerca de 15 segundos.

## Shiny (em construção)

A versão em Shiny lê os dados direto das Releases do GitHub e ajusta o modelo do João sob demanda, com as mesmas funções da página em Quarto. A etapa pronta é a dos dados; o app vem nas próximas.

- `sudo Rscript shiny/instalar_pacotes.R` instala os pacotes que faltam (`dlnm`, `nanoparquet`, `future` e os demais).
- `Rscript shiny/atualizar_cache.R` consulta a API de Releases e, se o SIM (`sim-mrj`) ou o HAAT (`clima-mrj`) mudaram, baixa os arquivos, monta o contexto e troca o cache em `shiny/cache/`. Sem versão nova, não baixa nada. Se o GitHub estiver fora do ar, mantém o cache. Opções: `--pop res,todos`, `--cache pasta`, `--forcar`.
- O download só é aceito com o tamanho igual ao que o GitHub informa, e a troca do cache é atômica: o app nunca lê arquivo pela metade. Mudar `R/funcoes.R` (as regras) também invalida o cache.
- No servidor, rode o script pelo usuário que executa os apps (`sudo -u shiny crontab -e`), por exemplo todo dia às 06:00. O Shiny Server derruba um app que passa de 60 s para iniciar, por isso o download não acontece dentro da sessão.
- Variáveis opcionais: `PAINEL_CACHE`, `PAINEL_SIM_REPOS`, `PAINEL_CLIMA_REPO` e `GITHUB_PAT` (só para subir o limite de 60 consultas por hora da API).

## Testes

```
Rscript testes/teste_funcoes.R
Rscript testes/teste_modelo.R
python3 testes/teste_pagina.py painel_figura1.html capturas/
PAINEL_TESTE_TAR=silver_sim_mrj.tar.gz PAINEL_TESTE_HAAT=haat_diario_municipal.csv Rscript testes/teste_fontes.R
```

O teste do download e do cache sobe um servidor local que imita a API e os arquivos das Releases e confere: primeira carga, versão igual (não baixa de novo), versão nova (troca e apaga a antiga), tamanho errado, GitHub fora do ar e bloqueio de atualização simultânea. Sem as variáveis de ambiente roda só os testes que não precisam de dados.

O teste do modelo simula uma série com efeito do calor conhecido e confere que o RR e o excesso de óbitos são recuperados. O teste da página percorre todos os recortes nas duas escalas e confere que o recorte muda o resultado.

## Limitações

- Estudo ecológico, descritivo e exploratório; um modelo por recorte, sem correção para comparações múltiplas.
- A faixa de 95% do esperado não inclui a incerteza dos coeficientes.
- Não há termo de dia da semana, como no modelo do João.
- O período de COVID entra no ajuste com um termo suave próprio, então o esperado nesse período não serve de comparação.
- O clima existe desde 17/04/2007; antes disso o calor entra como ausente.
