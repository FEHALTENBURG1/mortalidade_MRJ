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

## Testes

```
Rscript testes/teste_funcoes.R
Rscript testes/teste_modelo.R
python3 testes/teste_pagina.py painel_figura1.html capturas/
```

O teste do modelo simula uma série com efeito do calor conhecido e confere que o RR e o excesso de óbitos são recuperados. O teste da página percorre todos os recortes nas duas escalas e confere que o recorte muda o resultado.

## Limitações

- Estudo ecológico, descritivo e exploratório; um modelo por recorte, sem correção para comparações múltiplas.
- A faixa de 95% do esperado não inclui a incerteza dos coeficientes.
- Não há termo de dia da semana, como no modelo do João.
- O período de COVID entra no ajuste com um termo suave próprio, então o esperado nesse período não serve de comparação.
- O clima existe desde 17/04/2007; antes disso o calor entra como ausente.
