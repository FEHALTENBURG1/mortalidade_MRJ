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
  pop_txt <- if (M$pop == "res") "residentes no Rio que morreram no Rio" else "todos os óbitos ocorridos no Rio, residentes ou não"
  nc_txt <- if (length(M$meses_nc)) paste(mm(M$meses_nc), collapse = ", ") else "nenhum"
  h <- M$exposicoes$horas$ref; a <- M$exposicoes$haat$ref
  pg <- function(...) paste0(paste0(..., collapse = ""), "\n\n")

  intro <- if (demanda)
    "Esta página é a Figura 1 do painel em R e Shiny. O servidor lê os dados direto das Releases do GitHub e ajusta o modelo do recorte escolhido no momento em que você o seleciona (de 3 a 15 segundos na primeira vez). O resultado fica guardado no servidor, e as próximas consultas ao mesmo recorte, por qualquer pessoa, saem na hora até a próxima atualização dos dados. Cada combinação de local, faixa etária, raça/cor, causa do óbito e retiradas do ajuste tem o seu modelo."
  else
    "Esta página é a Figura 1 do painel reescrita em R e Quarto. O processamento dos dados e o modelo rodam em R (`calcular_figura1.R`), e o resultado fica embutido neste arquivo, que abre sozinho no navegador. Trocar um filtro não reestima nada: cada combinação de local, faixa etária e raça/cor já tem o seu modelo calculado."

  causas_p <- if (demanda)
    pg("O seletor Causa do óbito oferece quatro séries: causas naturais (o padrão, definido acima), todas as causas exceto COVID-19, todas as causas com COVID-19 e causas externas. Causas externas são os óbitos fora dos capítulos A a R da CID-10, sem a COVID-19: lesões e causas externas (capítulos S a Y) e registros sem CID válida. Cada causa tem a sua própria série de óbitos, e a lista de recortes com óbitos suficientes muda com ela.")
  else ""
  retirar_p <- if (demanda) paste0(
    "### Retirar períodos do ajuste\n\n",
    pg("Por padrão o ajuste segue o modelo do João: o período de COVID entra no ajuste, com o termo `s(COVID)` absorvendo o excesso; os meses de registro não consolidado entram no ajuste; e os dias sem clima entram como dias sem calor. Três caixas, em Retirar do ajuste do modelo, mudam isso. Cada caixa marcada tira os dias correspondentes dos dados usados para estimar o modelo (os dias sem registro no SIM saem sempre):"),
    "- Período COVID (", fd(M$covid[1]), " a ", fd(M$covid[2]), "): o modelo é ajustado sem esses dias e perde o termo `s(COVID)`.\n",
    "- Meses com registro não consolidado (", nc_txt, "): os dias desses meses saem do ajuste.\n",
    "- Dias sem dados de clima e os ", M$lag, " seguintes: sem a caixa, esses dias contam como dias sem calor. Com ela, saem do ajuste, junto com os ", M$lag, " dias depois de cada um, porque a defasagem de 0 a ", M$lag, " dias usa o clima dos dias anteriores.\n\n",
    pg("Semanas com algum dia fora do ajuste ficam sem esperado. Cada combinação de causa e de retiradas é um modelo diferente, ajustado e guardado no servidor na primeira vez que é pedido. A exigência de ", M$min_obitos, " óbitos conta só os dias que ficam no ajuste."))
  else ""

  pop_frase <- if (demanda) "A população selecionada são os" else "A população desta versão são os"

  trocas <- if (demanda)
    "A binomial negativa é a família padrão. Em séries muito esparsas, em que ela não converge, o ajuste usa quase-Poisson, e a nota abaixo da figura informa qual família foi usada em cada recorte."
  else
    paste0("Séries muito esparsas, em que a binomial negativa não converge, usam quase-Poisson. ",
           if (sum(unlist(resumo$n_qp)) == 0) "Nesta execução nenhum dos " else paste0(sum(unlist(resumo$n_qp)), " dos "),
           fmt(2 * resumo$n_segmentos), " ajustes precisou dessa troca.")

  rr_frase <- paste0("O RR acumulado mostrado nos quadros é o risco de viver os ", M$lag + 1, " dias (o dia e os 10 anteriores) no nível de referência, em relação a nenhum calor.",
                     if (!demanda) paste0(" Para todos os locais e idades, o RR com ", h[1], " h por dia é ", rr_txt(resumo$rr_total$horas[1:3]),
                                          " e com ", h[2], " h por dia é ", rr_txt(resumo$rr_total$horas[4:6]), "."))

  phi_frase <- if (demanda) "O valor de φ de cada recorte aparece na nota abaixo da figura."
               else paste0("Para todos os locais e idades, φ é ", fmt(resumo$phi_total$horas, 2), ".")

  repro <- if (demanda)
    paste0("```\nRscript shiny/atualizar_cache.R\n```\n\nO app Shiny e a página em Quarto usam as mesmas funções de R (pasta `R/`), então o mesmo recorte dá o mesmo resultado nos dois. ",
           "Pacotes de R: `shiny`, `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `future` e `promises`.")
  else
    paste0("```\nRscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv\nquarto render painel_figura1.qmd\n```\n\n",
           "Pacotes de R: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr`.")
  versao <- if (demanda)
    paste0(" Versão dos dados: SIM atualizado em ", dados$sim_atualizado, " (", dados$repo_sim, "), clima atualizado em ", dados$clima_atualizado, " (UTC); cache gerado em ", dados$gerado_em, ".")
  else paste0(" Versão dos dados desta página gerada em ", M$gerado_em, ".")

  paste0(
    "## Métodos e fontes\n\n",
    pg(intro),
    "### Dados\n\n",
    pg("Os óbitos vêm do Sistema de Informações sobre Mortalidade (SIM/DATASUS), pelo data lake do projeto (camada silver, óbitos ocorridos no município do Rio de Janeiro desde 2006). ",
        pop_frase, " ", pop_txt, ": ", fmt(M$n_obitos), " óbitos por causas naturais entre ", fd(M$inicio), " e ", fd(M$fim),
        ". Causa natural é o capítulo A a R da CID-10 sem a COVID-19 (B34 e códigos U)", if (demanda) "." else ", que ficam fora de todas as séries."),
    causas_p,
    pg("O local do óbito parte do campo LOCOCOR do SIM e é refinado pelo tipo do estabelecimento no CNES: tipos 5, 7, 15 e 62 contam como Hospital, tipos 20, 21 e 73 como UPA / pronto atendimento, e os demais estabelecimentos de saúde ficam em Outros estabelecimentos. Domicílio, via pública, outros locais e ignorado vêm direto do LOCOCOR."),
    pg("As faixas etárias seguem a UNICEF: 0-4, 5-9, 10-19, depois uma faixa por década até 79 anos e 80 anos ou mais. Os ", fmt(n_sem_idade), " óbitos sem idade informada entram só em Todas as idades."),
    pg("A raça/cor vem do campo RACACOR. Branca, preta e parda têm série própria, e o agregado PPI soma preta, parda e indígena. Indígena e amarela têm óbitos de menos para uma série própria, e os óbitos sem cor informada entram só em Todas. As séries por raça/cor valem para todas as idades."),
    pg("O clima é a série diária municipal `haat_diario_municipal.csv`, calculada a partir do lago de clima do projeto (INMET e Alerta Rio): média das estações por hora, índice de calor pela fórmula do National Weather Service (Rothfusz, 1990) e horas acima de cada limiar (HAAT). A metodologia segue Morais et al. (repositório *heat_mortality_MRJ_article*, usado com autorização). O clima existe desde abril de 2007; antes disso o calor entra nos modelos como ausente."),
    "### Período e registro do SIM\n\n",
    pg("A série termina no menor entre o último dia com óbito no SIM e o último dia com clima. Dias sem nenhum óbito registrado (", fmt(M$dias_sem_registro),
        " dias) são arquivo ainda não carregado, e não observações de zero óbitos: saem do ajuste e aparecem em cinza claro."),
    pg("Meses com taxa diária de óbitos abaixo de 80% da mediana dos 12 meses de referência anteriores são marcados como registro não consolidado (", nc_txt, ", ", fmt(M$dias_nc),
        " dias). Eles continuam no ajuste", if (demanda) " por padrão", " e aparecem hachurados, porque o número observado pode estar abaixo do real",
        if (demanda) "; a caixa Meses com registro não consolidado, em Retirar do ajuste do modelo, tira esses meses do ajuste e o esperado deixa de ser traçado neles", ". A taxa do mês é o número de óbitos dividido pelos dias com algum óbito registrado; meses de COVID e meses já marcados não entram na referência."),
    "### O modelo\n\n",
    pg("Cada recorte (local por faixa etária, ou local por raça/cor) e cada medida de calor têm um modelo próprio, o modelo do João (script `02_model_fitting.R` do repositório citado), ajustado com `mgcv::gam` por REML. Os óbitos de cada dia seguem uma binomial negativa:"),
    "```\nlog(mu_t) = a + cb(calor, defasagem 0 a 10) + s(tempo) + s(dia do ano) + s(COVID)\n```\n\n",
    "- `cb` é a cross-basis do pacote `dlnm`: uma função da exposição ao calor combinada com uma função da defasagem (spline natural com 3 graus de liberdade), de 0 a ", M$lag, " dias.\n",
    "- `s(tempo)` é um spline de placa fina com ", M$k_tempo, " nós, que acompanha a tendência de longo prazo. O modelo do João usa 12 nós para 12,5 anos; aqui o número de nós cresce na mesma proporção para a série mais longa.\n",
    "- `s(dia do ano)` é um spline cíclico com 6 nós (sazonalidade anual).\n",
    "- `s(COVID)` é um spline cíclico com 8 nós sobre o número de dias desde o início do período de COVID (", fd(M$covid[1]), " a ", fd(M$covid[2]), "), igual a zero fora dele.", if (demanda) " Com a caixa do período COVID marcada, esse termo sai do modelo.", "\n",
    "- Não há termo de dia da semana, como no modelo do João.\n\n",
    pg(trocas),
    pg("Duas medidas de calor estão disponíveis no seletor:"),
    "| Medida | Variável | Resposta à exposição | Níveis de referência do RR |\n|:--|:--|:--|:--|\n",
    "| Horas | horas do dia com índice de calor ≥ 36 °C | spline natural, 1 gl | ", h[1], " e ", h[2], " h por dia |\n",
    "| HAAT | graus-hora acima de 36 °C no dia (`auc36`) | spline penalizado, 15 gl | ", a[1], " e ", a[2], " °C·h por dia |\n\n",
    pg(rr_frase),
    retirar_p,
    "### Esperado sem calor\n\n",
    pg("O esperado de cada dia é o preditor linear do modelo com a cross-basis trocada pela cross-basis de exposição zero em todas as defasagens, isto é, o que o modelo prevê se não houvesse calor. O esperado semanal é a soma dos sete esperados diários da semana. A faixa de 95% usa a soma das variâncias diárias (mu + mu²/theta), multiplicada por uma dispersão semanal φ (no mínimo 1) e uma aproximação normal. Dias vizinhos têm resíduos correlacionados, por epidemias e outros eventos que o modelo não descreve, e a soma de variâncias independentes subestima a variância da semana; φ é a razão entre o erro quadrático semanal e essa soma, medida nos resíduos do modelo ajustado e fora do período de COVID. ",
        phi_frase, " Semanas com algum dia fora do ajuste ficam sem esperado."),
    pg("Como cada recorte tem o seu modelo, o esperado e a razão observado ÷ esperado mudam quando o filtro muda."),
    "### Comparação entre semanas de calor e as demais\n\n",
    pg("Semana de calor é a que tem pelo menos 3 dias com índice de calor máximo ≥ 36 °C (ou pelo menos um dia em NC2 a NC5 do protocolo, conforme o seletor). A razão é a soma dos óbitos observados dividida pela soma dos esperados sem calor nas semanas do grupo, sem COVID, sem semanas sem registro e sem clima. Na escala diária, dia exposto é o dia de calor (pelo menos 4 h com índice de calor ≥ 36 °C) e os três dias seguintes. O modelo usa defasagem de até 10 dias, então parte do efeito cai também em dias fora desse contorno."),
    "### O que mudou em relação ao painel anterior\n\n",
    pg("Na Figura 1 semanal do painel em Python, a linha esperada vinha de um modelo só de tendência e sazonalidade, sem o calor, ajustado a todas as semanas. Esse modelo se ajusta à média dos dados, inclusive nas semanas de calor, e por isso a razão observado ÷ esperado ficava perto de 1,00 em qualquer recorte. Aqui o esperado é o contrafactual de um modelo que estima o efeito do calor em cada recorte, e a razão nas semanas de calor reflete esse efeito."),
    "### Limitações\n\n",
    "- É um estudo ecológico de séries temporais, descritivo e exploratório.\n",
    "- Cada recorte tem um modelo, sem correção para comparações múltiplas. Recortes com poucos óbitos (mínimo de ", M$min_obitos, " no ajuste) dão RR instáveis, com intervalos largos.\n",
    "- A faixa de 95% não inclui a incerteza dos coeficientes do modelo.\n",
    "- O período de COVID é absorvido por um termo suave, então o esperado nele não serve de comparação e as semanas e os dias de COVID ficam fora dos indicadores.", if (demanda) " Com a caixa de retirada marcada, o período fica sem esperado.", "\n",
    if (demanda) "- Os óbitos são contados e não há taxa por população: o modelo não usa a população como offset, e o spline de tempo absorve a mudança lenta dela ao longo dos anos. O RR não depende disso, mas a comparação de níveis entre populações ou entre anos pede uma taxa.\n",
    "- Antes de 17/04/2007 não há clima, e o calor entra como ausente.\n",
    "- As demais abas do painel em Python (RR por faixa e defasagem, horas por limiar, CIDs, unidades, clima) seguem com o modelo anterior e serão migradas uma a uma.\n\n",
    "### Reprodução\n\n",
    repro, versao, "\n\n",
    "Paleta de cores baseada no site EpiRio (Centro de Inteligência Epidemiológica, Prefeitura do Rio). Biblioteca de gráficos: Chart.js 4.4.1, embutida ", if (demanda) "neste painel" else "neste arquivo", ".\n")
}
