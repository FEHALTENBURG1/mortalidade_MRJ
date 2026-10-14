# Painel Mortalidade × Calor (Shiny)

O app lê tabelas pré-calculadas direto do Release `painel-mrj` do GitHub (FEHALTENBURG1/mortalidade_MRJ). Ele só filtra e desenha;
todo o cálculo está em Python, na pasta `painel/` (começa em `painel/nucleo.py`, que contém o modelo, as máscaras de período e o erro-padrão robusto).
O workflow `atualizar_painel.yml` baixa o silver do SIM (Release `sim-mrj`) e o HAAT do clima (Release `clima-mrj`, repositório FEHALTENBURG1/Dados_clima_MRJ),
recalcula tudo e republica o Release `painel-mrj`, que também recebe o painel HTML autocontido (`painel_calor_mrj.html`).
O app recarrega as tabelas a cada 6 h (`PAINEL_TTL_HORAS`) e o período exibido vem de `meta.json`.

O texto completo de métodos (pergunta, hipóteses, fórmula, passo a passo de um RR, limitações, referências) está na aba “Métodos e fontes” do painel HTML.
Neste app a aba de métodos traz o resumo e os números que o sustentam (`metodos_numeros.json`).

## Pacotes
shiny, bslib, readr, dplyr, tidyr, ggplot2, plotly, DT, jsonlite (R ≥ 4.1, por causa do `|>`); leaflet para o mapa de unidades (sem ele, a aba mostra um aviso).

## Variáveis de ambiente (opcionais)
- `PAINEL_DADOS_URL`: base dos arquivos (padrão: Release `painel-mrj`).
- `PAINEL_DADOS_LOCAL`: pasta local com as tabelas (para testes sem internet).
- `PAINEL_HTML_URL`: endereço do painel HTML (link na aba de métodos).
- `PAINEL_TTL_HORAS`: validade do cache (padrão 6).

## Rodar
```r
shiny::runApp("painel_shiny")
```
Teste local: `python painel/painel_pipeline.py --silver <silver> --haat haat_diario_municipal.csv --aux painel/dados_auxiliares --saida painel_dados`
e `PAINEL_DADOS_LOCAL=painel_dados`.

## Tabelas lidas (geradas por `painel/exportar_painel.py`)
`semanas.csv`, `serie_semanal.csv.gz`, `rr_local_faixa.csv`, `heatmap_horas.csv`, `defasagem.csv`, `cid_rr.csv.gz`, `cid_semanal.csv.gz`, `cid_nomes.csv`,
`unidades.csv`, `bairros.csv`, `unid_janela.csv.gz`, `clima_diario.csv`, `clima_anual.csv`, `gam.csv`, `metodos_numeros.json`, `meta.json`.

Também são publicadas as tabelas por janela de anos (`janelas_grade.csv`, `janelas_rr.csv.gz`, `janelas_lag.csv.gz`, `janelas_heat.csv.gz`, `janelas_cid.csv.gz`) a coluna `nivel_calor` (NC1 a NC5) em `clima_diario.csv` e a série diária desde 2006 de óbitos observados e esperados sem calor, por local e faixa etária e por definição de calor (`serie_diaria.csv.gz`).
Esta versão do app Shiny ainda não usa essas tabelas: o seletor de período por janela de anos, as colunas coloridas pelo Nível de Calor e a escala diária da Figura 1 estão só no painel HTML.
