# Painel de mortalidade e calor em R e Quarto: Figura 1

Versão em R e Quarto da Figura 1 do painel (óbitos por causas naturais contra o número esperado sem calor, Rio de Janeiro). O painel em Python permanece inalterado; esta pasta cobre apenas a Figura 1, e as demais abas serão migradas gradualmente.

O resultado é um arquivo HTML único (`painel_figura1.html`), sem servidor: o R ajusta os modelos, grava os resultados em JSON e o Quarto embute tudo na página. Os filtros (local do óbito, faixa etária, raça/cor, escala semanal ou diária, medida de calor, período) só escolhem entre modelos já calculados.

## O que mudou

- Modelo. Cada recorte tem um modelo adaptado do modelo de Morais et al. (GAM com `mgcv` e cross-basis do `dlnm`, defasagem de 0 a 10 dias, binomial negativa), ajustado apenas aos óbitos daquele recorte. O esperado é o contrafactual sem calor desse modelo. No painel anterior a linha esperada da figura semanal vinha de um modelo só de tendência e sazonalidade, o que deixava a razão observado ÷ esperado perto de 1,00 em qualquer recorte.
- Faixas etárias, definidas para este estudo: 0-4, 5-9, 10-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79 e 80+.
- Registro não consolidado. Mesma regra do painel em Python: meses abaixo de 80% da mediana de referência ficam no ajuste e aparecem hachurados; dias sem nenhum óbito no SIM saem do ajuste.
- Duas medidas de calor. Horas por dia com índice de calor ≥ 36 °C (spline natural, 1 grau de liberdade) e HAAT, os graus-hora acima de 36 °C (spline penalizado, 15 graus de liberdade).

## Estrutura

```
calcular_figura1.R        driver: lê o SIM e o clima, ajusta os modelos e grava saida/figura1_<pop>.json
R/funcoes.R               óbitos (nanoparquet), causas, local, raça/cor, faixas, registro do SIM, clima, semanas
R/modelo_joao.R           GAM + DLNM por segmento, contrafactual, esperado semanal e curvas de exposição-resposta
R/exportar.R              JSON da figura (inteiro ou por recorte) e bloco compactado para a página
R/metodos.R               texto da aba Métodos e fontes, igual no Quarto e no Shiny
R/fontes_remotas.R        Shiny: baixa o SIM e o HAAT das Releases do GitHub e mantém o cache em disco
R/servico.R               Shiny: ajuste de um recorte sob demanda, cache de ajustes e pedidos assíncronos
shiny/                    Shiny: app.R, atualizar_cache.R (cron), instalar_pacotes.R e a pasta cache/ (fora do Git)
painel_figura1.qmd        página (métodos em texto, números calculados em R)
assets/                   CSS, JavaScript da figura (figura1.js) e das abas do app (aba_*.js, aba_*.html), Chart.js e markup dos filtros
dados_auxiliares/         cnes_estab.csv (tipo dos estabelecimentos)
testes/                   testes das funções, do modelo (dados simulados), da página e do app (Playwright), das fontes e do serviço
```

## Como rodar

Pacotes de R: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr`. Quarto 1.4 ou mais novo. O app Shiny também usa `shiny`, `future`, `promises` e `commonmark`.

```
Rscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv
quarto render painel_figura1.qmd
```

- `--silver`: pasta `silver` do data lake do SIM (`sim/ocorrencia_mrj/ano_arquivo=*/part-0.parquet`).
- `--haat`: `haat_diario_municipal.csv` da Release `clima-mrj`.
- `--pop res` (padrão, residentes com óbito ocorrido no Rio) ou `--pop todos`. Para a página usar `todos`, defina `PAINEL_POP=todos` antes de `quarto render`.
- `--cores N`: processos em paralelo (no Windows roda em um só).
- `--reusar`: não reajusta; refaz só o JSON a partir de `saida/modelos_<pop>.rds`.

São cerca de 90 recortes por medida de calor; o ajuste leva alguns minutos por medida. A leitura do SIM leva cerca de 15 segundos.

## Shiny

O app Shiny (`shiny/app.R`) lê os dados direto das Releases do GitHub e ajusta o modelo de referência quando o recorte é escolhido, com as mesmas funções de R da página em Quarto. Por enquanto só tem a Figura 1. A página traz os mesmos filtros, mais a escolha da população (residentes ou todos os óbitos ocorridos no Rio).

Como funciona:

1. `shiny/atualizar_cache.R` (rodado por cron, fora das sessões) consulta a API de Releases e, se o SIM (`sim-mrj`) ou o HAAT (`clima-mrj`) mudaram, baixa os arquivos, monta o contexto de cada população e troca o cache em `shiny/cache/`. Sem versão nova, não baixa nada. Se o GitHub estiver fora do ar, mantém o cache.
2. Ao abrir, a página recebe só o calendário e o clima (cerca de 90 KB compactados). Nenhum modelo é ajustado nessa hora.
3. Ao escolher local, faixa etária, raça/cor, medida de calor, causa do óbito e retiradas do ajuste, o navegador pede o recorte ao servidor. Um trabalhador (processo separado do `future`) ajusta só esse modelo, em geral em 2 a 9 segundos nos testes locais (a interface informa de 3 a 15 segundos, para cobrir servidores mais lentos), e o resultado vai para `shiny/cache/ajustes/<versão dos dados>/`. O mesmo recorte, pedido de novo por qualquer pessoa, é lido do disco, sem novo ajuste. O navegador também guarda o que já recebeu.
4. Quando o cron traz uma versão nova dos dados, os ajustes da versão antiga são apagados. Quem estava com a página aberta vê o aviso para recarregar.

### Causa do óbito e retiradas do ajuste

Dois filtros existem só no app. O primeiro é a causa do óbito: causas naturais (padrão), todas as causas exceto COVID-19, todas as causas com COVID-19 e causas externas (óbitos fora dos capítulos A a R da CID-10, sem COVID-19). O segundo é um conjunto de três caixas, em "Retirar do ajuste do modelo":

| Caixa | Efeito no ajuste |
|:--|:--|
| Período COVID | os dias do período saem do ajuste e o modelo perde o termo `s(COVID)` |
| Meses com registro não consolidado | os dias desses meses saem do ajuste |
| Dias sem dados de clima | esses dias e os 10 seguintes saem do ajuste (sem a caixa, contam como dias sem calor) |

Sem nenhuma caixa marcada, o ajuste é o do modelo de referência. Os dias sem registro no SIM saem sempre. Cada combinação de causa e de caixas é um modelo diferente, guardado em disco como os demais (`<causa>`, o código de três dígitos 0/1 das caixas e o recorte entram no nome do arquivo). O mínimo de 300 óbitos conta só os dias que ficam no ajuste. O cache de dados passou a guardar também os óbitos de outras causas (cerca de 10 MB por população), então a primeira atualização depois desta versão refaz o cache: `Rscript shiny/atualizar_cache.R --forcar`.

### Abas do app

O app tem uma aba por assunto, todas ajustadas pelo mesmo modelo (GAM com DLNM) e com filtros próprios de causa do óbito e de retirada do ajuste. A população vale para todas e fica acima das abas. Cada aba é um par `assets/aba_<nome>.html` e `assets/aba_<nome>.js`, registrado em `ABAS` no `shiny/app.R`; o script recebe de `figura1.js` um objeto com os pedidos ao servidor, os filtros e os textos comuns.

| Aba | Conteúdo |
|:--|:--|
| Série de óbitos | Figura 1: observados e esperados sem calor, semanal e diária |
| Exposição-resposta e defasagem | Figura 2: RR acumulado em 0 a 10 dias pela exposição; Figura 3: gráfico de floresta com o RR de cada defasagem (lag 0 a 10) e o RR acumulado (0 a 1, 0 a 3, 0 a 7 e 0 a 10), nos dois níveis de referência; Figura 4: mapa de RR por horas no dia (H) e limiar do índice de calor (K), um modelo por célula. O seletor Comparar com (local do óbito) põe dois locais lado a lado, com a mesma escala nas Figuras 2 e 3 |
| Causas específicas (CID-10) | Figura 5: gráfico de floresta com o RR de cada causa básica de 3 caracteres (pelo menos 1.500 óbitos nos dias do ajuste), com valor q de Benjamini e Hochberg dentro do conjunto e do capítulo escolhidos; Figura 5b: série semanal da causa escolhida. A medida de calor e o nível de exposição são escolhidos na aba |

O mapa da Figura 4 tem 104 células (13 limiares, de 32 a 44 °C, e 8 níveis de horas). Cada célula é um GAM com DLNM próprio, com a exposição binária "pelo menos H horas com índice de calor ≥ K" (`ajustar_mapa_limiar()` em `R/modelo_joao.R`). O app pede uma coluna por limiar (medida `mapa32` a `mapa44`), no máximo duas ao mesmo tempo, e cada coluna leva cerca de 15 segundos na primeira vez; depois fica no cache em disco como qualquer outro ajuste. `Rscript shiny/atualizar_cache.R --aquecer` calcula de antemão as colunas do recorte inicial.

Na aba de causas, cada causa é um modelo próprio, ajustado à série diária dela (`ajustar_pedido_cid()` em `R/servico.R`). O app pede primeiro a lista de causas do recorte (pedido `cidlista`), depois uma causa por vez (`cid_<CID>_<horas|haat>`, no máximo duas ao mesmo tempo) e, só quando o usuário clica em uma causa, a série semanal dela (`cidsem_<CID>_<horas|haat>`). Cada resposta de causa traz só o RR, o IC 95%, o valor de p e a contagem de óbitos; o valor q é calculado no navegador quando todas as causas da família estão prontas. Os nomes das causas ficam em `dados_auxiliares/cid_nomes.json`. Como a aba precisa da causa básica de cada óbito, `enxugar_contexto()` em `R/funcoes.R` passou a guardar a coluna `cid` no cache de dados, e por isso o cache inteiro precisa ser refeito uma vez (`atualizar_cache.R --forcar`). Para deixar a aba pré-calculada no recorte inicial, `atualizar_cache.R --aquecer-cid` ajusta cada causa para as duas medidas (de 15 a 30 minutos por população na primeira vez; pode rodar com `nohup` em segundo plano).

As curvas vêm do mesmo ajuste de cada recorte (`curvas_modelo()` em `R/modelo_joao.R`), então um recorte já pedido na Figura 1 abre na hora na aba de exposição-resposta. Os ajustes guardados em disco levam uma versão do formato (`VERSAO_AJUSTE` em `R/servico.R`): um ajuste gravado por versão anterior é refeito ao ser pedido.

Instalação no servidor (exemplo com o repositório em `/opt/mortalidade_MRJ`, dono `shiny`):

```
cd /opt/mortalidade_MRJ && sudo -u shiny git pull
sudo Rscript painel_quarto/shiny/instalar_pacotes.R
sudo -u shiny Rscript painel_quarto/shiny/atualizar_cache.R
sudo ln -s /opt/mortalidade_MRJ/painel_quarto/shiny /srv/shiny-server/mortalidade_calor
sudo -u shiny crontab -e     # 0 6 * * *  /usr/bin/Rscript /opt/mortalidade_MRJ/painel_quarto/shiny/atualizar_cache.R >> /opt/mortalidade_MRJ/painel_quarto/shiny/cache/cron.log 2>&1
```

O app abre em `http://servidor:3838/mortalidade_calor/`. O Shiny Server encerra um app que leva mais de 60 s para iniciar, por isso o download não acontece dentro da sessão. Se alguém abrir o app sem cache, ele dispara a atualização em segundo plano e a página é atualizada automaticamente quando os dados estiverem prontos.

Rodar localmente: `PAINEL_CACHE=pasta_do_cache Rscript -e 'shiny::runApp("shiny")'` a partir desta pasta. Para montar um cache sem rede a partir de arquivos locais: `Rscript testes/montar_cache_local.R --silver pasta/silver --haat haat_diario_municipal.csv --cache pasta_do_cache --pop res,todos`.

Variáveis de ambiente (todas opcionais): `PAINEL_RAIZ` (pasta do projeto, se o app não localizar a pasta automaticamente), `PAINEL_CACHE`, `PAINEL_TRABALHADORES` (modelos ajustados ao mesmo tempo, padrão 2; cada trabalhador usa cerca de 300 MB), `PAINEL_SIM_REPOS`, `PAINEL_CLIMA_REPO` e `GITHUB_PAT` (só para subir o limite de 60 consultas por hora da API).

O download só é aceito com o tamanho igual ao que o GitHub informa, e a troca do cache é atômica: o app nunca lê arquivo pela metade. Mudar `R/funcoes.R` (as regras) também invalida o cache.

## Testes

```
Rscript testes/teste_funcoes.R
Rscript testes/teste_modelo.R
python3 testes/teste_pagina.py painel_figura1.html capturas/
PAINEL_TESTE_TAR=silver_sim_mrj.tar.gz PAINEL_TESTE_HAAT=haat_diario_municipal.csv Rscript testes/teste_fontes.R
PAINEL_CACHE=pasta_do_cache PAINEL_TESTE_BASE=saida/figura1_res.json Rscript testes/teste_servico.R
PAINEL_CACHE=pasta_do_cache python3 testes/teste_app.py
```

O teste do download e do cache sobe um servidor local que imita a API e os arquivos das Releases e confere: primeira carga, versão igual (não baixa de novo), versão nova (troca e apaga a antiga), tamanho errado, GitHub fora do ar e bloqueio de atualização simultânea. Sem as variáveis de ambiente roda só os testes que não precisam de dados.

O teste do serviço compara o resultado de cada recorte ajustado sob demanda com o do `calcular_figura1.R` (referência gerada com os mesmos dados), confere o cache em disco, os códigos de erro e os pedidos assíncronos. O teste do app sobe o Shiny e percorre a página no navegador: figura inicial, troca de filtros, causa do óbito e retiradas do ajuste, população, recorte sem óbitos suficientes, outra sessão lendo do disco e aviso de dados novos.

O teste do modelo simula uma série com efeito do calor conhecido e confere que o RR e o excesso de óbitos são recuperados. O teste da página percorre todos os recortes nas duas escalas e confere que o recorte muda o resultado.

## Limitações

- Estudo ecológico, descritivo e exploratório; um modelo por recorte, sem correção para comparações múltiplas.
- A faixa aproximada de variação de 95% do esperado não inclui a incerteza dos coeficientes e não tem cobertura garantida (ver o Quadro 5 da Figura 1 para a cobertura por período).
- Não há termo de dia da semana, como no modelo de referência.
- O período de COVID entra no ajuste com um termo suave próprio, então o esperado nesse período não serve de comparação. No app, a caixa de retirada remove o período do ajuste e deixa o esperado sem traçado nele.
- Os óbitos são contados e não há taxa por população: o modelo não usa a população como offset, e o spline de tempo absorve a mudança lenta dela ao longo dos anos. O RR não depende disso, mas comparar níveis entre populações ou entre anos pede uma taxa.
- O clima existe desde 17/04/2007; antes disso o calor entra como ausente.
