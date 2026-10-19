# Texto da aba "Métodos e fontes", em markdown, usado pela página em Quarto e pelo app Shiny.
#
# Uma só fonte para os dois: a diferença está em quatro frases que dependem de como os modelos são ajustados.
#   - Quarto (resumo != NULL): todos os recortes foram ajustados antes, então o texto cita contagens e valores do recorte "Todos os locais, todas as idades".
#   - Shiny (resumo = NULL): os modelos são ajustados quando o recorte é escolhido; o texto explica isso e remete à nota abaixo da figura.

fmt <- function(x, d = 0) formatC(x, format = "f", digits = d, big.mark = ".", decimal.mark = ",")
fd <- function(x) format(as.Date(x), "%d/%m/%Y")
mm <- function(ym) paste0(substr(ym, 6, 7), "/", substr(ym, 1, 4))
rr_txt <- function(v) sprintf("%s (IC 95%%: %s a %s)", fmt(v[1], 2), fmt(v[2], 2), fmt(v[3], 2))

# M: meta da Figura 1 (base_figura1); n_sem_idade: óbitos sem idade informada;
# resumo: resumo_figura1() (só no Quarto); dados: list(sim_atualizado, clima_atualizado, repo_sim, gerado_em) (só no Shiny)
texto_metodos <- function(M, n_sem_idade, resumo = NULL, dados = NULL) {
  demanda <- is.null(resumo)
  pop_txt <- if (M$pop == "res") "residentes no Rio com óbito ocorrido no próprio município" else "todos os óbitos ocorridos no Rio, residentes ou não"
  nc_txt <- if (length(M$meses_nc)) paste(mm(M$meses_nc), collapse = ", ") else "nenhum"
  h <- M$exposicoes$horas$ref; a <- M$exposicoes$haat$ref
  pg <- function(...) paste0(paste0(..., collapse = ""), "\n\n")

  intro <- if (demanda)
    "Esta página apresenta a Figura 1 do painel, desenvolvido em R e Shiny. O servidor obtém os dados diretamente das Releases do GitHub e ajusta o modelo de cada recorte (combinação de filtros) no momento em que ele é selecionado (de 3 a 15 segundos na primeira solicitação). O resultado é armazenado no servidor, de modo que as consultas seguintes ao mesmo recorte, feitas por qualquer usuário, são atendidas de imediato até a próxima atualização dos dados. Cada combinação de local do óbito, faixa etária, raça/cor, causa do óbito e retiradas do ajuste tem um modelo próprio."
  else
    "Esta página apresenta a Figura 1 do painel, reescrita em R e Quarto. O processamento dos dados e o ajuste dos modelos são feitos em R (`calcular_figura1.R`), e os resultados ficam incorporados a este arquivo, que abre diretamente no navegador. Como cada recorte (combinação de local do óbito, faixa etária e raça/cor) já tem o seu modelo calculado, a troca de filtros não reestima os modelos."

  causas_p <- if (demanda)
    pg("O seletor Causa do óbito oferece quatro séries: causas naturais (padrão, definidas acima), todas as causas exceto COVID-19, todas as causas com COVID-19 e causas externas. Neste painel, causas externas são os óbitos fora dos códigos A00 a R99 da CID-10 e sem COVID-19, o que inclui lesões e demais causas externas (códigos S a Y) e registros sem CID válida. Cada causa tem a sua própria série de óbitos, e a lista de recortes com óbitos suficientes varia conforme a causa.")
  else ""
  retirar_p <- if (demanda) paste0(
    "### Retirar períodos do ajuste\n\n",
    pg("Por padrão, o ajuste segue o modelo de referência (Morais et al.): o período da COVID-19 permanece no ajuste, com o termo `s(COVID)` absorvendo o excesso; os meses de registro não consolidado permanecem no ajuste; e os dias sem dados de clima entram como dias sem calor. Três caixas de seleção, no grupo Retirar do ajuste do modelo, alteram esse padrão. Cada caixa marcada exclui os dias correspondentes dos dados usados para estimar o modelo (os dias sem registro no SIM são sempre excluídos):"),
    "- Período da COVID-19 (", fd(M$covid[1]), " a ", fd(M$covid[2]), "): o modelo é ajustado sem esses dias e deixa de ter o termo `s(COVID)`.\n",
    "- Meses com registro não consolidado (", nc_txt, "): os dias desses meses são excluídos do ajuste.\n",
    "- Dias sem dados de clima e os ", M$lag, " seguintes: sem a caixa marcada, esses dias contam como dias sem calor. Com ela, são excluídos do ajuste, junto com os ", M$lag, " dias posteriores a cada um, porque a defasagem de 0 a ", M$lag, " dias usa o clima dos dias anteriores.\n\n",
    pg("Semanas com algum dia fora do ajuste ficam sem esperado. Cada combinação de causa e de retiradas corresponde a um modelo distinto, ajustado e armazenado no servidor na primeira solicitação. O mínimo de ", M$min_obitos, " óbitos considera apenas os dias mantidos no ajuste."))
  else ""

  curvas_p <- if (demanda) paste0(
    "### Curvas de exposição-resposta e de defasagem\n\n",
    pg("A aba Exposição-resposta e defasagem mostra, para o recorte escolhido, duas figuras obtidas do mesmo modelo que gera o esperado sem calor. A Figura 2 traz o RR acumulado em 0 a ", M$lag, " dias em função da exposição, mantida constante em todos os dias da janela, em relação a nenhuma exposição. O intervalo de confiança de 95% usa a matriz de covariância dos coeficientes da cross-basis (função `crosspred` do pacote `dlnm`). A grade de exposição vai de zero ao percentil 99 dos dias com exposição, porque acima disso há poucos dias. A Figura 3 é um gráfico de floresta, nos dois níveis de referência: a parte superior traz o RR de cada defasagem de 0 a ", M$lag, " (efeito da exposição ocorrida l dias antes do óbito) e a parte inferior traz o RR acumulado de 0 até l, para l igual a 1, 3, 7 e ", M$lag, ". O RR acumulado até l é o produto dos RR por defasagem de 0 a l, com intervalo de confiança de 95% a partir da matriz de covariância dos coeficientes, e as duas partes usam escalas horizontais diferentes. Os quadros do topo trazem o RR no mesmo dia (lag 0) e os RR acumulados em 0 a 3 e em 0 a ", M$lag, " dias."),
    pg("Com a medida de horas, a resposta à exposição tem 1 grau de liberdade, de modo que o logaritmo do RR é linear na exposição por construção e a curva não identifica limiar. O HAAT, com spline penalizado de 15 graus de liberdade, permite curvatura. A aba tem filtros próprios de recorte, causa do óbito e retirada do ajuste, e reaproveita os modelos já ajustados nas outras abas."),
    pg("O seletor Comparar com (local do óbito) acrescenta um segundo recorte, que difere do primeiro apenas no local do óbito: os demais filtros valem para os dois. Os recortes aparecem em colunas, cada um com quadros, Figuras 2, 3 e 4 e interpretação próprios, e as Figuras 2 e 3 usam a mesma escala nos dois lados. O texto de comparação traz o RR acumulado dos dois locais e informa se os intervalos de confiança se sobrepõem, o que é uma comparação informal e não um teste da diferença. Quando um dos recortes é Todos os locais, ele inclui os óbitos do outro e as duas estimativas não são independentes."))
  else ""

  mapa_p <- if (demanda) paste0(
    "### Mapa de horas por dia e limiar do índice de calor\n\n",
    pg("A Figura 4 refaz, com o modelo de referência, o mapa de horas por dia e limiar da versão anterior do painel. Para cada limiar K (32 a 44 °C) e cada número mínimo de horas H (1, 2, 3, 4, 6, 8, 10 e 12), a exposição é binária: vale 1 nos dias com pelo menos H horas de índice de calor igual ou superior a K, e 0 nos demais, inclusive nos dias sem dado de clima. Cada célula é um modelo próprio, com o mesmo GAM da Figura 1 (binomial negativa, spline do tempo, ciclo anual e termo do período COVID) e a mesma defasagem de 0 a ", M$lag, " dias, com cross-basis linear na exposição e spline natural de 3 graus de liberdade na defasagem. O RR de cada célula é o acumulado em 0 a ", M$lag, " dias para a exposição mantida em todos os ", M$lag + 1, " dias, em relação a nenhum dia exposto, com intervalo de confiança de 95% a partir da matriz de covariância dos coeficientes."),
    pg("A versão anterior definia a exposição como um dia com a condição em t, t−1, t−2 ou t−3 e estimava cada célula por quase-Poisson com termo de dia da semana. O modelo atual usa a defasagem distribuída do DLNM e não tem termo de dia da semana, de modo que os RR das duas versões não são comparáveis em valor. Células com menos de 15 dias expostos no ajuste, ou com menos de 30 dias sem exposição, não são estimadas. As 104 células são ajustadas de forma independente, são aninhadas por construção (um dia com mais horas também entra nas definições com menos horas) e não passam por correção para comparações múltiplas; o mapa é descritivo. As colunas são calculadas sob demanda, uma por limiar, e ficam guardadas no servidor para os pedidos seguintes."))
  else ""

  cid_p <- if (demanda) paste0(
    "### Causas específicas (CID-10)\n\n",
    pg("A aba Causas específicas (CID-10) estima, para o recorte escolhido, o RR em dias de calor de cada causa básica de óbito com 3 caracteres da CID-10. Cada causa com pelo menos ", fmt(M$cid_min), " óbitos nos dias do ajuste é avaliada em um modelo próprio, com a estrutura do modelo de referência (binomial negativa, spline do tempo, ciclo anual, termo do período da COVID-19 quando restam dias dele no ajuste e cross-basis de defasagem de 0 a ", M$lag, " dias), aplicado à série diária de óbitos daquela causa e com as mesmas retiradas do ajuste do recorte. A medida de calor e o nível de exposição (um dos dois níveis de referência) são escolhidos na aba. O RR é o acumulado em 0 a ", M$lag, " dias para a exposição mantida em todos os ", M$lag + 1, " dias, em relação a nenhuma exposição. O IC 95% usa a matriz de covariância dos coeficientes, e o valor de p vem da aproximação normal do logaritmo do RR."),
    pg("Como a aba avalia dezenas de causas de uma só vez, parte dos RR diferentes de 1 apareceria por acaso. A correção de Benjamini e Hochberg controla a taxa de falsas descobertas dentro da família formada pelas causas do conjunto e do capítulo escolhidos, e o valor q resultante só é calculado quando todas as causas da família estão estimadas. As causas com q < 0,05 ficam destacadas, e uma caixa permite incluir as demais, em cinza. Mudar o conjunto ou o capítulo muda a família e, portanto, o q. O conjunto Lista a priori é uma lista fixa, definida no código e independente dos resultados: reúne as causas dos capítulos A-B, E, F, G, I, J e N da CID-10, mais R95 a R99, X30 e W65 a W74. As neoplasias podem servir de comparação, porque não se espera efeito agudo do calor sobre elas, e um RR diferente de 1 nelas sugere variação temporal que o modelo não capturou."),
    pg("Cada causa é pedida ao servidor separadamente, no máximo duas ao mesmo tempo, e o resultado fica guardado em disco. Por isso a figura se completa causa a causa, e a primeira abertura de um recorte leva de 3 a 10 segundos por causa. Ao clicar em uma causa, a Figura 5b mostra seus óbitos semanais observados e o esperado sem calor do modelo daquela causa, com a faixa de 95% calculada como na Figura 1. Os nomes das causas vêm do arquivo `dados_auxiliares/cid_nomes.json`, que cobre as causas de 3 caracteres avaliadas."))
  else ""

  pop_frase <- if (demanda) "A população selecionada corresponde a" else "A população desta versão corresponde a"

  trocas <- if (demanda)
    "A família binomial negativa é a padrão. Em séries muito esparsas, nas quais ela não converge, o ajuste usa a família quase-Poisson, e a nota abaixo da figura informa a família utilizada em cada recorte."
  else
    paste0("Séries muito esparsas, nas quais a binomial negativa não converge, usam a família quase-Poisson. ",
           if (sum(unlist(resumo$n_qp)) == 0) "Nesta execução, nenhum dos " else paste0("Nesta execução, ", sum(unlist(resumo$n_qp)), " dos "),
           fmt(2 * resumo$n_segmentos), if (sum(unlist(resumo$n_qp)) <= 1) " ajustes precisou dessa troca." else " ajustes precisaram dessa troca.")

  rr_frase <- paste0("O risco relativo (RR) acumulado apresentado nos indicadores corresponde à exposição ao nível de referência de calor em todos os ", M$lag + 1, " dias (o dia e os 10 anteriores), em relação à ausência de calor.",
                     if (!demanda) paste0(" Para todos os locais e idades, o RR com ", h[1], " h por dia é ", rr_txt(resumo$rr_total$horas[1:3]),
                                          " e com ", h[2], " h por dia é ", rr_txt(resumo$rr_total$horas[4:6]), "."))

  phi_frase <- if (demanda) "O valor de φ de cada recorte aparece na nota abaixo da figura."
               else paste0("Para todos os locais e idades, φ é ", fmt(resumo$phi_total$horas, 2), ".")

  repro <- if (demanda)
    paste0("```\nRscript shiny/atualizar_cache.R\n```\n\nO aplicativo Shiny e a página em Quarto utilizam as mesmas funções de R (pasta `R/`); assim, o mesmo recorte produz o mesmo resultado nos dois. ",
           "Pacotes de R: `shiny`, `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `future` e `promises`.")
  else
    paste0("```\nRscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv\nquarto render painel_figura1.qmd\n```\n\n",
           "Pacotes de R: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr`.")
  versao <- if (demanda)
    paste0(" Versão dos dados: SIM atualizado em ", dados$sim_atualizado, " (", dados$repo_sim, ") e clima atualizado em ", dados$clima_atualizado, " (horários em UTC); cache gerado em ", dados$gerado_em, ".")
  else paste0(" Versão dos dados desta página: gerada em ", M$gerado_em, ".")

  paste0(
    "## Métodos e fontes\n\n",
    pg(intro),
    "### Dados\n\n",
    pg("Os óbitos provêm do Sistema de Informações sobre Mortalidade (SIM/DATASUS), por meio do repositório de dados (data lake) do projeto, em sua camada silver, com os óbitos ocorridos no município do Rio de Janeiro desde 2006. ",
        pop_frase, " ", pop_txt, ": ", fmt(M$n_obitos), " óbitos por causas naturais entre ", fd(M$inicio), " e ", fd(M$fim),
        ". Causa natural é aquela registrada nos capítulos I a XVIII da CID-10 (códigos A00 a R99), exceto a COVID-19 (B34 e códigos U)", if (demanda) "." else ". Os óbitos por COVID-19 ficam fora de todas as séries."),
    causas_p,
    pg("O local do óbito parte do campo LOCOCOR do SIM e é refinado pelo tipo de estabelecimento registrado no Cadastro Nacional de Estabelecimentos de Saúde (CNES): os tipos 5, 7, 15 e 62 correspondem a Hospital; os tipos 20, 21 e 73, a UPA / pronto atendimento (UPA: Unidade de Pronto Atendimento); e os demais estabelecimentos de saúde, a Outros estabelecimentos. Domicílio, via pública, outros locais e ignorado são os registrados diretamente no LOCOCOR."),
    pg("As faixas etárias, definidas para este estudo, são 0-4, 5-9, 10-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79 e 80 anos ou mais. Os ", fmt(n_sem_idade), " óbitos sem idade informada entram apenas em Todas as idades."),
    pg("A raça/cor provém do campo RACACOR. Branca, preta e parda têm série própria, e o agregado PPI reúne preta, parda e indígena. As categorias indígena e amarela não têm óbitos suficientes para série própria, e os óbitos com raça/cor ignorada ou não informada entram apenas em Todas. As séries por raça/cor são calculadas para todas as idades."),
    pg("O clima é a série diária municipal `haat_diario_municipal.csv`, calculada a partir do repositório de dados climáticos do projeto (Instituto Nacional de Meteorologia, INMET, e Alerta Rio): média horária das estações, índice de calor pela equação do National Weather Service dos Estados Unidos (Rothfusz, 1990) e horas acima de cada limiar (HAAT). A metodologia segue Morais et al. (repositório *heat_mortality_MRJ_article*, usado com autorização). Há dados de clima a partir de abril de 2007; antes disso, o calor entra nos modelos como ausente."),
    "### Período e registro do SIM\n\n",
    pg("A série termina na menor das duas datas: o último dia com óbito registrado no SIM e o último dia com dados de clima. Os dias sem nenhum óbito registrado (", fmt(M$dias_sem_registro),
        " dias) correspondem a arquivo ainda não carregado: são excluídos do ajuste e aparecem em cinza claro."),
    pg("Meses com taxa diária de óbitos inferior a 80% da mediana dos 12 meses de referência anteriores são classificados como registro não consolidado (", nc_txt, "; ", fmt(M$dias_nc),
        " dias). Esses meses permanecem no ajuste", if (demanda) " por padrão", " e aparecem hachurados, porque o número observado pode estar abaixo do real",
        if (demanda) "; a caixa Meses com registro não consolidado, no grupo Retirar do ajuste do modelo, exclui esses meses do ajuste, e o esperado deixa de ser traçado neles", ". A taxa do mês é o número de óbitos dividido pelo número de dias com algum óbito registrado; os meses do período da COVID-19 e os já classificados como não consolidados não compõem a referência."),
    "### O modelo\n\n",
    pg("Cada recorte (local do óbito por faixa etária, ou local do óbito por raça/cor) e cada medida de calor têm um modelo próprio, adaptado do modelo de Morais et al. (script `02_model_fitting.R` do repositório citado acima): um modelo aditivo generalizado (GAM) com defasagens distribuídas (DLNM), ajustado com `mgcv::gam` por máxima verossimilhança restrita (REML). Os óbitos de cada dia seguem uma distribuição binomial negativa:"),
    "```\nlog(mu_t) = a + cb(calor, defasagem 0 a 10) + s(tempo) + s(dia do ano) + s(COVID)\n```\n\n",
    "- `cb` é a base cruzada (cross-basis) do pacote `dlnm`: uma função da exposição ao calor combinada com uma função da defasagem (spline natural com 3 graus de liberdade, gl), de 0 a ", M$lag, " dias.\n",
    "- `s(tempo)` é um spline de placa fina com base de dimensão k = ", M$k_tempo, ", que acompanha a tendência de longo prazo. O modelo de referência usa k = 12 para 12,5 anos; aqui, k cresce na mesma proporção para a série mais longa.\n",
    "- `s(dia do ano)` é um spline cíclico com base de dimensão k = 6 (sazonalidade anual).\n",
    "- `s(COVID)` é um spline cíclico com base de dimensão k = 8 sobre o número de dias desde o início do período da COVID-19 (", fd(M$covid[1]), " a ", fd(M$covid[2]), "), com valor zero fora dele.", if (demanda) " Se a caixa do período da COVID-19 estiver marcada, esse termo é retirado do modelo.", "\n",
    "- O modelo não inclui termo de dia da semana, como no modelo de referência.\n\n",
    pg(trocas),
    pg("O seletor oferece duas medidas de calor:"),
    "| Medida | Variável | Resposta à exposição | Níveis de referência do RR |\n|:--|:--|:--|:--|\n",
    "| Horas | horas do dia com índice de calor ≥ 36 °C | spline natural, 1 gl | ", h[1], " e ", h[2], " h por dia |\n",
    "| HAAT | graus-hora acima de 36 °C no dia (`auc36`) | spline penalizado, 15 gl | ", a[1], " e ", a[2], " °C·h por dia |\n\n",
    pg(rr_frase),
    retirar_p,
    curvas_p,
    mapa_p,
    cid_p,
    "### Esperado sem calor\n\n",
    pg("O esperado de cada dia é o preditor linear do modelo com a cross-basis substituída pela cross-basis de exposição zero em todas as defasagens, isto é, o número de óbitos que o modelo prevê na ausência de calor (contrafactual). O esperado semanal é a soma dos sete esperados diários da semana (semanas epidemiológicas completas, de domingo a sábado). A faixa de 95% usa uma aproximação normal, com variância igual à soma das variâncias diárias (μ + μ²/θ) multiplicada por uma dispersão semanal φ (no mínimo 1). Dias vizinhos têm resíduos correlacionados, por epidemias e outros eventos que o modelo não descreve, e a soma de variâncias independentes subestima a variância da semana. O fator φ é a razão entre o erro quadrático semanal e essa soma, medida nos resíduos do modelo ajustado e fora do período da COVID-19. ",
        phi_frase, " Semanas com algum dia fora do ajuste ficam sem esperado."),
    pg("Como cada recorte tem modelo próprio, o esperado e a razão observado ÷ esperado variam conforme os filtros selecionados."),
    "### Comparação entre semanas de calor e as demais\n\n",
    pg("Semana de calor é aquela com pelo menos 3 dias de índice de calor máximo ≥ 36 °C (ou com pelo menos um dia em NC2 a NC5, os níveis de calor 2 a 5 do protocolo de calor da Prefeitura do Rio de Janeiro, Decreto Rio nº 54.740/2024, conforme o critério selecionado). A razão é a soma dos óbitos observados dividida pela soma dos esperados sem calor nas semanas do grupo, excluídas as semanas do período da COVID-19, as sem registro no SIM e as sem dados de clima. Na escala diária, dia exposto é o dia de calor (pelo menos 4 h com índice de calor ≥ 36 °C) e os três dias seguintes. Como o modelo usa defasagens de até 10 dias, parte do efeito ocorre também em dias fora desse intervalo de quatro dias."),
    "### O que mudou em relação ao painel anterior\n\n",
    pg("Na Figura 1 semanal do painel em Python, o esperado era obtido por um modelo apenas de tendência e sazonalidade, sem a variável de calor, ajustado a todas as semanas. Como esse modelo se ajusta à média dos dados, inclusive nas semanas de calor, a razão observado ÷ esperado ficava próxima de 1,00 em qualquer recorte. Nesta versão, o esperado é o contrafactual de um modelo que estima o efeito do calor em cada recorte, e a razão nas semanas de calor reflete esse efeito."),
    "### Limitações\n\n",
    "- É um estudo ecológico de séries temporais, descritivo e exploratório.\n",
    "- Cada recorte tem um modelo próprio, sem correção para comparações múltiplas. Recortes com poucos óbitos (mínimo de ", M$min_obitos, " no ajuste) produzem RR instáveis, com intervalos de confiança largos.\n",
    "- A faixa de 95% não inclui a incerteza dos coeficientes do modelo.\n",
    "- O período da COVID-19 é absorvido por um termo suave; por isso, o esperado nesse período não serve de comparação, e as semanas e os dias desse período ficam fora dos indicadores.", if (demanda) " Se a caixa de retirada estiver marcada, o período fica sem esperado.", "\n",
    if (demanda) "- Os modelos analisam contagens de óbitos, sem taxas por população: a população não entra como offset, e o spline de tempo absorve a variação lenta dela ao longo dos anos. A comparação de níveis entre populações ou entre anos exigiria taxas; o RR independe dessa limitação.\n",
    "- Não há dados de clima antes de 17/04/2007; nesse período, o calor entra no modelo como ausente.\n",
    "- As demais abas do painel em Python (RR por faixa e defasagem, horas por limiar, CIDs, unidades e clima) ainda utilizam o modelo anterior e serão migradas gradualmente.\n\n",
    "### Reprodução\n\n",
    repro, versao, "\n\n",
    "A paleta de cores foi adaptada do site EpiRio (Centro de Inteligência Epidemiológica, Prefeitura do Rio). Os gráficos são gerados com a biblioteca Chart.js 4.4.1, incorporada ", if (demanda) "a este painel" else "a este arquivo", ".\n")
}
