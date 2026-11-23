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
  sec <- function(titulo, ...) paste0("### ", titulo, "\n\n", paste0(..., collapse = ""))

  intro <- if (demanda)
    "O servidor ajusta o modelo de cada recorte (combinação de filtros) quando ele é selecionado, em até 15 segundos na primeira vez, e guarda o resultado até a próxima atualização dos dados."
  else
    "Esta página foi gerada em R e Quarto (`calcular_figura1.R`): os modelos de todos os recortes são ajustados antes e incorporados ao arquivo."

  dados_p <- paste0(
    pg("Óbitos: SIM/DATASUS, camada silver do data lake do projeto, ocorridos no município do Rio de Janeiro desde 2006. ", if (demanda) "A população selecionada" else "A população desta versão", " corresponde a ", pop_txt, ": ", fmt(M$n_obitos), " óbitos por causas naturais (CID-10 A00 a R99, exceto COVID-19: B34 e códigos U) entre ", fd(M$inicio), " e ", fd(M$fim), ".",
       if (demanda) " O seletor Causa do óbito inclui também todas as causas exceto COVID-19, todas com COVID-19 e causas externas (óbitos fora de A00 a R99 e sem COVID-19, o que inclui os códigos S a Y e registros sem CID válida)." else " Os óbitos por COVID-19 ficam fora de todas as séries."),
    pg("Local do óbito: campo LOCOCOR do SIM, refinado pelo tipo de estabelecimento no CNES (Hospital: tipos 5, 7, 15 e 62; UPA / pronto atendimento: 20, 21 e 73; demais: Outros estabelecimentos). Faixas etárias: 0-4, 5-9, 10-19 e, de dez em dez anos, até 80 ou mais; os ", fmt(n_sem_idade), " óbitos sem idade entram só em Todas as idades. Raça/cor (RACACOR): branca, preta e parda têm série própria, e o agregado PPI reúne preta, parda e indígena; amarela e ignorada entram só em Todas. As séries por raça/cor valem para todas as idades."),
    pg("Clima: série diária municipal `haat_diario_municipal.csv`, do repositório de dados climáticos do projeto (INMET e Alerta Rio): índice de calor pela equação do National Weather Service dos Estados Unidos (Rothfusz, 1990) e horas acima de cada limiar (HAAT), com a metodologia de Morais et al. (repositório *heat_mortality_MRJ_article*, usado com autorização). Antes de 17/04/2007 não há clima, e o calor entra como ausente."),
    pg("A série termina na menor das datas entre o último óbito no SIM e o último dia com clima. Os ", fmt(M$dias_sem_registro), " dias sem óbito registrado (arquivo não carregado) saem do ajuste e aparecem em cinza claro. Meses com taxa diária de óbitos abaixo de 80% da mediana dos 12 meses de referência anteriores (sem os meses da COVID-19 e os não consolidados) são de registro não consolidado (", nc_txt, "; ", fmt(M$dias_nc), " dias) e aparecem hachurados",
       if (demanda) "; por padrão ficam no ajuste." else "; ficam no ajuste."))

  modelo_p <- paste0(
    pg("Cada recorte e cada medida de calor têm um modelo próprio, adaptado de Morais et al. (`02_model_fitting.R` do repositório citado): GAM com defasagens distribuídas (DLNM), `mgcv::gam` com REML, família binomial negativa",
       if (demanda) " (quase-Poisson nas séries esparsas em que ela não converge; a nota da figura informa a família):"
       else paste0(" (quase-Poisson nas séries esparsas em que ela não converge: ", if (sum(unlist(resumo$n_qp)) == 0) "nenhum" else sum(unlist(resumo$n_qp)), " dos ", fmt(2 * resumo$n_segmentos), " ajustes desta execução):")),
    "```\nlog(mu_t) = a + cb(calor, defasagem 0 a 10) + s(tempo) + s(dia do ano) + s(COVID)\n```\n\n",
    "- `cb`: cross-basis do `dlnm`, com spline penalizado na exposição (tabela abaixo) e spline natural de 3 gl na defasagem de 0 a ", M$lag, " dias.\n",
    "- `s(tempo)`: spline de placa fina, k = ", M$k_tempo, " (k = 12 para 12,5 anos no modelo de referência, proporcional à série).\n",
    "- `s(dia do ano)`: spline cíclico, k = 6. `s(COVID)`: spline cíclico, k = 8, sobre os dias desde o início do período da COVID-19 (", fd(M$covid[1]), " a ", fd(M$covid[2]), "), zero fora dele. Sem termo de dia da semana, como no modelo de referência.\n\n",
    "| Medida | Variável | Resposta à exposição | Níveis de referência do RR |\n|:--|:--|:--|:--|\n",
    "| Horas | horas do dia com índice de calor ≥ 36 °C | spline penalizado, até ", M$exposicoes$horas$df, " gl | ", h[1], " e ", h[2], " h por dia |\n",
    "| HAAT | graus-hora acima de 36 °C no dia (`auc36`) | spline penalizado, até ", M$exposicoes$haat$df, " gl | ", a[1], " e ", a[2], " °C·h por dia |\n\n",
    pg("O RR acumulado é o de uma exposição ao nível de referência mantida nos ", M$lag + 1, " dias (o dia e os ", M$lag, " anteriores), em relação a nenhuma exposição.",
       if (!demanda) paste0(" Para todos os locais e idades, o RR com ", h[1], " h por dia é ", rr_txt(resumo$rr_total$horas[1:3]), " e com ", h[2], " h por dia é ", rr_txt(resumo$rr_total$horas[4:6]), ".")),
    pg("O esperado sem calor é o preditor do modelo com a exposição zerada em todas as defasagens; o semanal soma os sete diários (semanas de domingo a sábado). A faixa de 95% usa aproximação normal, com a soma das variâncias diárias (μ + μ²/θ) multiplicada pela dispersão semanal φ (mínimo 1), medida nos resíduos fora da COVID-19, porque dias vizinhos têm resíduos correlacionados. ",
       if (demanda) "O φ de cada recorte está na nota da figura." else paste0("Para todos os locais e idades, φ é ", fmt(resumo$phi_total$horas, 2), "."),
       " Semanas com algum dia fora do ajuste ficam sem esperado."))

  calor_p <- pg("Semana de calor: pelo menos 3 dias com índice de calor máximo ≥ 36 °C ou, conforme o critério escolhido, pelo menos um dia em NC2 a NC5. Os níveis de calor (NC) são os do protocolo da Prefeitura do Rio (Decreto Rio nº 54.740/2024), reconstruídos só com valores observados e com o corte incluindo o limiar (o decreto diz “acima de”): NC2, pelo menos 4 h ≥ 36 °C em 1 ou 2 dias seguidos; NC3, o mesmo por 3 dias seguidos ou mais; NC4, pelo menos 4 h ≥ 40 °C dentro de uma sequência de NC3; NC5, pelo menos 2 h ≥ 44 °C dentro de uma sequência de NC3. Não substitui o nível divulgado pelo COR-Rio. ",
                "A razão observado ÷ esperado é a soma dos observados pela soma dos esperados sem calor nas semanas do grupo, sem as semanas da COVID-19, sem registro no SIM ou sem clima. Na escala diária, dia exposto é o dia de calor (pelo menos 4 h ≥ 36 °C) e os três seguintes; como a defasagem vai a ", M$lag, " dias, parte do efeito cai fora desse intervalo.")

  retirar_p <- if (demanda) paste0(
    sec("Retirar períodos do ajuste",
        pg("Por padrão, a COVID-19 (termo `s(COVID)`) e os meses de registro não consolidado ficam no ajuste, e os dias sem clima contam como dias sem calor. As caixas do grupo Retirar do ajuste do modelo excluem: o período da COVID-19 (", fd(M$covid[1]), " a ", fd(M$covid[2]), "), sem o termo `s(COVID)`; os meses não consolidados; e os dias sem clima e os ", M$lag, " seguintes, que dependem desse clima pela defasagem. Dias sem registro no SIM saem sempre. O mínimo de ", M$min_obitos, " óbitos conta só os dias mantidos.")),
    sec("Período de análise",
        pg("Ano inicial e Ano final (anos civis inteiros, mínimo de ", PERIODO_MIN_ANOS, ") reajustam o modelo só com os dias do período: RR, IC 95% e esperado valem para ele. O k do spline de tempo é proporcional ao número de dias (mínimo 6), `s(COVID)` só entra com pelo menos 30 dias da COVID-19, a cross-basis usa o clima real dos dias anteriores ao início, e semanas que cruzam o limite ficam sem esperado.")),
    sec("Poder estatístico, curvas e comparativo",
        pg("Por padrão, só aparecem estimativas com poder estatístico: IC 95% do RR que não inclui 1 (na aba de causas, q < 0,05); a caixa Mostrar também o que não tem poder estatístico exibe as demais, em cinza, e o IC fica na dica do cursor. Ocultar é um recurso de exibição, não uma conclusão: um IC que inclui 1 não demonstra ausência de efeito, e o conjunto do que passa no critério tende a superestimar o efeito."),
        pg("Curvas de exposição-resposta e de defasagem (Figuras 2 e 3): vêm do mesmo modelo do esperado, com IC 95% pela matriz de covariância da cross-basis (`crosspred`, do `dlnm`); a grade de exposição vai até o percentil 99 dos dias com exposição, e o RR acumulado de 0 até l é o da exposição mantida nesses dias. A resposta à exposição é suave e só se afasta de uma reta onde os dados sustentam a curvatura."),
        pg("Comparar lado a lado acrescenta um lado B que difere do A em uma dimensão (local, faixa etária, raça/cor, medida de calor, causa, período ou retirada do ajuste); a comparação por raça/cor fixa a faixa etária em Todas as idades. A sobreposição dos IC é uma comparação informal, não um teste da diferença, e as estimativas não são independentes quando um recorte contém o outro.")),
    sec("Mapa de horas por limiar e causas específicas",
        pg("Figura 4: para cada limiar K (32 a 44 °C) e número mínimo de horas H (1, 2, 3, 4, 6, 8, 10 e 12), a exposição é binária (1 nos dias com pelo menos H horas de índice de calor ≥ K). Cada uma das 104 células é um modelo próprio, como o da Figura 1, com cross-basis linear na exposição; células com menos de 15 dias expostos ou 30 sem exposição não são estimadas. As células são aninhadas e sem correção para comparações múltiplas, e o mapa é descritivo."),
        pg("Figura 5: cada causa básica de 3 caracteres com pelo menos ", fmt(M$cid_min), " óbitos nos dias do ajuste tem um modelo próprio, como o da Figura 1, com o RR acumulado em 0 a ", M$lag, " dias e o p pela aproximação normal do log do RR. A correção de Benjamini e Hochberg controla a taxa de falsas descobertas na família formada pelas causas do conjunto e do capítulo escolhidos (q só é calculado com todas estimadas), e q < 0,05 define o que é mostrado por padrão. Nomes: `dados_auxiliares/cid_nomes.json`. O conjunto Causas selecionadas do referencial reúne os 15 grupos de Morais et al.: influenza e pneumonia (J09, J12 a J18); respiratórias crônicas inferiores (J40 a J47); outras respiratórias (J00 a J06, J20 a J39, J60 a J70, J80 a J99, R09, U04); hipertensivas (I10 a I15); isquêmicas do coração (I20 a I25); insuficiência cardíaca (I50); cerebrovasculares (I60 a I69); outras do aparelho circulatório (I00 a I09, I26 a I49, I51, I52, I70 a I99); neoplasias malignas (C00 a C97); Alzheimer e demência (G30, G31, F01, F03); diabetes (E10 a E14); insuficiência renal (N17 a N19); sepse (A40, A41); infecção urinária (N39); causas mal definidas (R).")))
  else ""

  limitacoes <- paste0(
    "- Estudo ecológico de séries temporais, descritivo e exploratório; um modelo por recorte, sem correção para comparações múltiplas", if (demanda) " (exceto na aba de causas)", ". Com poucos óbitos (mínimo de ", M$min_obitos, " no ajuste), os RR são instáveis e os IC, largos.\n",
    "- A faixa de 95% não inclui a incerteza dos coeficientes.\n",
    "- O período da COVID-19 é absorvido por um termo suave: o esperado nele não serve de comparação, e suas semanas e dias ficam fora dos indicadores.\n",
    if (demanda) "- Os modelos analisam contagens, sem taxas por população (sem offset; o spline de tempo absorve a variação lenta dela). O RR independe disso, mas comparar níveis entre populações ou anos exigiria taxas.\n",
    if (!demanda) "- As demais abas do painel em Python (RR por faixa e defasagem, horas por limiar, CIDs, unidades e clima) ainda utilizam o modelo anterior e serão migradas gradualmente.\n",
    "\n")

  repro <- if (demanda)
    paste0("```\nRscript shiny/atualizar_cache.R\n```\n\nMesmas funções de R (pasta `R/`) no app e na página em Quarto. Pacotes: `shiny`, `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `future` e `promises`.")
  else
    paste0("```\nRscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv\nquarto render painel_figura1.qmd\n```\n\nPacotes: `mgcv`, `dlnm`, `nanoparquet`, `jsonlite`, `knitr`.")
  versao <- if (demanda)
    paste0(" Versão dos dados: SIM atualizado em ", dados$sim_atualizado, " (", dados$repo_sim, ") e clima atualizado em ", dados$clima_atualizado, " (horários em UTC); cache gerado em ", dados$gerado_em, ".")
  else paste0(" Versão dos dados desta página: gerada em ", M$gerado_em, ".")

  paste0(
    "## Métodos e fontes\n\n",
    pg(intro),
    sec("Dados", dados_p),
    sec("O modelo", modelo_p),
    sec("Semanas de calor e níveis de calor", calor_p),
    retirar_p,
    sec("Limitações", limitacoes),
    sec("Reprodução", repro, versao, "\n\n"),
    "Paleta adaptada do EpiRio (Centro de Inteligência Epidemiológica, Prefeitura do Rio); gráficos com a biblioteca Chart.js 4.4.1, incorporada ", if (demanda) "a este painel" else "a este arquivo", ".\n")
}
