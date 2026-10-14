# Mortalidade (SIM) no município do Rio de Janeiro: data lake e painel clima × óbitos

## O que tem aqui
- `sim_datalake.py`: baixa os CSVs do SIM (OpenDATASUS), filtra o MRJ (330455) e grava Parquet (silver) por ocorrência e por residência.
- `.github/workflows/atualizar_sim.yml`: atualização mensal automática; publica na Release `sim-mrj` o silver (`silver_sim_mrj.tar.gz`) e `obitos_diarios_ocorrencia_mrj.csv`.
- `painel/`: cálculo do painel (Python: modelo quase-Poisson com erro-padrão robusto, ver `painel/nucleo.py`) e painel HTML autocontido; `painel_shiny/`: app Shiny que lê as tabelas pré-calculadas.
- `.github/workflows/atualizar_painel.yml`: recalcula o painel a partir do silver do SIM e do HAAT do clima e publica o Release `painel-mrj`.

- `clima_datalake.py`: série histórica de clima do MRJ (INMET e Alerta Rio), um conjunto de dados por tipo de aferição.
- `.github/workflows/atualizar_clima.yml`: atualização mensal do clima; publica na Release `clima-mrj` (repositório FEHALTENBURG1/Dados_clima_MRJ).

## Primeira carga
Actions > "Atualizar SIM (MRJ)" > Run workflow, com os anos de 2006 a 2026 no campo `anos`.

## Painel
- HTML autocontido: `painel_calor_mrj.html`, no Release `painel-mrj` (e em `docs/`, se a variável de repositório `PUBLICAR_PAGES` for `true`).
- Shiny: copiar `painel_shiny/` para `/srv/shiny-server/painel`; instalar os pacotes listados em `painel_shiny/README.md`.
- Fontes do workflow `atualizar_painel.yml`, lidas por endereço público dos Releases: o silver do SIM (`sim-mrj`, arquivo `silver_sim_mrj.tar.gz`) vem do repositório que tiver o arquivo mais recente entre `FEHALTENBURG1/Dados_clima_MRJ` e `FEHALTENBURG1/mortalidade_MRJ` (variável de repositório `SIM_REPOS`, nomes separados por espaço); o HAAT do clima (`clima-mrj`, `haat_diario_municipal.csv`) vem de `FEHALTENBURG1/Dados_clima_MRJ` (variável `CLIMA_REPO`). O log do passo "Baixar silver do SIM e HAAT do clima" mostra de onde veio cada arquivo.
- Período da análise: o painel HTML tem seletores "De / Até" (anos civis inteiros). Cada janela é recalculada no workflow por `painel/janelas.py`, que refaz o modelo do zero; o navegador só escolhe entre as tabelas prontas. A grade padrão é `completa` (horas × limiar e CIDs em todas as janelas, mais de uma hora de cálculo); ao rodar o workflow à mão, a opção `pesada = reduzida` calcula essas duas abas só nas janelas que começam no primeiro ano ou terminam no último.
- Figura 1: colunas diárias com o índice de calor do dia, coloridas pelos Níveis de Calor NC1 a NC5 do protocolo da Prefeitura (reconstruídos a partir das colunas `num_hr_36`, `num_hr_40` e `num_hr_44` do HAAT; ver seção 16 dos Métodos).
- Figura 1: a mortalidade (semanal e diária) começa em 2006, primeiro ano do SIM no data lake; os modelos de RR das outras abas começam em 2012. Na escala diária cada dia é um ponto, com traço até o esperado sem calor (vermelho acima, azul abaixo). O esperado vem de `painel/serie1.py`: um modelo por combinação de local e faixa etária, com o calor em t, t−1, t−2 e t−3 (definição à escolha: IC máx. ≥ 36 °C, anomalia térmica ou NC2 a NC5) e o calor zerado. A tabela completa sai em `serie_diaria.csv.gz` no Release `painel-mrj`.
- Raça/cor na Figura 1: filtro por local × raça/cor (branca, preta, parda e o agregado PPI = preta + parda + indígena; todas as idades), a partir do campo `RACACOR` do SIM. `nucleo.classificar_raca` e `nucleo.series_local_raca` montam as séries e `painel/serie1.py` ajusta um modelo para cada uma. Indígena e amarela têm óbitos de menos para série própria (a indígena entra só no PPI). `teste_nucleo.py` confere a classificação e o agregado.
- Teste local do cálculo: `python painel/painel_pipeline.py --silver <silver> --haat haat_diario_municipal.csv --aux painel/dados_auxiliares`.

## Análises dos artigos (local do óbito)
- `painel/artigos.py`: gera as tabelas dos quatro artigos (razão de RR entre locais do óbito, defasagem de 0 a 7 dias, definições de calor, idade e capítulos da CID-10). Usa o mesmo núcleo do painel (`painel/nucleo.py`).
- Rodar depois de `painel_pipeline.py`, dentro da pasta de trabalho que ele cria (`trabalho_painel`, que já recebe uma cópia dos scripts): `cd trabalho_painel && python -I artigos.py` para todas as partes, ou `python -I artigos.py idade cap capx` para algumas. Partes: `desc locais lag defs sens idade cap capx cv`. As saídas ficam em `analise/artigos/*.csv`.
- `painel/teste_nucleo.py` confere o cálculo contra o statsmodels, inclusive a razão de RR entre locais (domicílio ÷ hospital: 1,0726 nos dois).

## Créditos
Clima e métrica HAAT: Morais JHA, Saraceni V, Ferreira CD, Cruz DMO, Aguilar GM, Cruz OG.
*Heat exposure and mortality in Rio de Janeiro: sustaining the first Brazilian heat protocol.*
https://github.com/joaohmorais/heat_mortality_MRJ_article (uso autorizado).

## Clima (data lake)
Variáveis: temperatura (média, máxima e mínima da hora), ponto de orvalho, umidade, precipitação, pressão,
vento (velocidade, direção, rajada) e radiação. Para cada uma:

| Camada | Caminho | Conteúdo |
|---|---|---|
| Horário | `clima/horario/<variavel>/ano=AAAA` | por estação, hora em UTC |
| Diário | `clima/diario/<variavel>/ano=AAAA` | por estação e dia local (UTC-3) |
| Municipal | `clima/municipal/<variavel>/ano=AAAA` | média das estações do município por dia local |

Também saem `clima/estacoes.csv`, `qa/resumo_clima.csv` e `clima_municipal_diario.csv` (tabela larga).

Estações: INMET A602 Marambaia, A621 Vila Militar, A636 Jacarepaguá, A652 Forte de Copacabana; Alerta Rio
Vidigal, Irajá, Jardim Botânico, Barra/Riocentro, Guaratiba, Santa Cruz, Alto da Boa Vista, São Cristóvão.
Nem toda estação mede todas as variáveis (a maior parte do Alerta Rio mede só temperatura, umidade e chuva);
`n_estacoes` mostra quantas entraram em cada média.

Primeira carga: Actions > "Atualizar clima (MRJ)" > Run workflow com os anos de 2006 a 2026.
