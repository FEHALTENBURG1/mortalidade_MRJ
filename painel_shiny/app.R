# Painel Mortalidade x Calor, Município do Rio de Janeiro
# Lê as tabelas pré-calculadas (Python, pasta painel/) direto do Release do GitHub. O cálculo está em painel/nucleo.py;
# este app só filtra e desenha. O texto completo de métodos, hipóteses e limitações está na aba "Métodos e fontes" do painel HTML.
suppressPackageStartupMessages({library(shiny); library(bslib); library(readr); library(dplyr); library(tidyr)
  library(ggplot2); library(plotly); library(DT)})   # jsonlite só com ::, porque jsonlite::validate mascararia shiny::validate
if (requireNamespace("leaflet", quietly = TRUE)) suppressPackageStartupMessages(library(leaflet))

# ---------- fonte dos dados ----------
BASE  <- Sys.getenv("PAINEL_DADOS_URL", "https://github.com/FEHALTENBURG1/mortalidade_MRJ/releases/download/painel-mrj")
LOCAL <- Sys.getenv("PAINEL_DADOS_LOCAL", "")        # pasta local opcional (testes)
HTML_PAINEL <- Sys.getenv("PAINEL_HTML_URL", "https://fehaltenburg1.github.io/mortalidade_MRJ/painel_calor_mrj.html")
TTL_H <- as.numeric(Sys.getenv("PAINEL_TTL_HORAS", "6"))
CACHE <- file.path(tempdir(), "painel_cache"); dir.create(CACHE, showWarnings = FALSE)

baixar <- function(nome) {
  if (nzchar(LOCAL)) return(file.path(LOCAL, nome))
  dest <- file.path(CACHE, nome)
  velho <- !file.exists(dest) || difftime(Sys.time(), file.mtime(dest), units = "hours") > TTL_H
  if (velho) {
    ok <- tryCatch({download.file(paste0(BASE, "/", nome), dest, mode = "wb", quiet = TRUE); TRUE}, error = function(e) FALSE, warning = function(w) FALSE)
    if (!ok && !file.exists(dest)) stop("Não foi possível baixar ", nome, " de ", BASE)
  }
  dest
}
ler  <- function(nome, ...) read_csv(baixar(nome), show_col_types = FALSE, progress = FALSE, ...)
meta <- jsonlite::fromJSON(baixar("meta.json"), simplifyVector = TRUE)
met  <- jsonlite::fromJSON(baixar("metodos_numeros.json"), simplifyVector = TRUE)

semanas <- ler("semanas.csv") |> mutate(ini = as.Date(ini))
serie   <- ler("serie_semanal.csv.gz") |> mutate(ini = as.Date(ini))
rr_lf   <- ler("rr_local_faixa.csv")
heat    <- ler("heatmap_horas.csv")
lagtab  <- ler("defasagem.csv")
clima   <- ler("clima_diario.csv") |> mutate(dia = as.Date(dia))
anual   <- ler("clima_anual.csv")
gam     <- ler("gam.csv")
cid_rr  <- ler("cid_rr.csv.gz")
cid_sem <- ler("cid_semanal.csv.gz") |> mutate(ini = as.Date(ini))
cid_nm  <- ler("cid_nomes.csv")
unid    <- ler("unidades.csv", col_types = cols(cnes = col_character(), .default = col_guess()))     # CNES tem 7 dígitos com zeros à esquerda: manter como texto
bairros <- ler("bairros.csv")
unid_j  <- ler("unid_janela.csv.gz", col_types = cols(cnes = col_character(), .default = col_guess())) |> mutate(dia = as.Date(dia))

POPS   <- c("Residentes no Rio que morreram no Rio (padrão)" = "res", "Todos os óbitos ocorridos no Rio" = "todos")
LOCAIS <- c("Todos os locais", "Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais")
FAIXAS <- c("Todas as idades", "<1 ano", "1 ano", "2–5", "6–10", "11–20", "21–30", "31–40", "41–50", "51–60", "61–70", "71–80", "81+")
PERIODOS <- c("Sem COVID", "Todo o período")
DEFS   <- unlist(meta$definicoes)                       # na ordem do cálculo: anomalia térmica, calor intenso
T_DIA <- "Dia de calor (lag 0–3)"; T_ISO <- "Dia de calor isolado"; T_ONDA <- "Onda de calor (≥2 dias)"
LAGS  <- c(paste0("lag", 0:7), "cum01", "cum03", "cum07")

fr   <- function(x, d = 2) formatC(x, format = "f", digits = d, decimal.mark = ",")
fn   <- function(x) format(round(x), big.mark = ".", decimal.mark = ",", scientific = FALSE)
frci <- function(r, l, h) sprintf("%s (IC 95%%: %s a %s)", fr(r), fr(l), fr(h))
dt   <- function(x) format(as.Date(x), "%d/%m/%Y")
pct  <- function(x, d = 1) paste0(fr(100 * x, d), "%")
`%||%` <- function(a, b) if (is.null(a) || length(a) == 0) b else a
AZUL <- "#164191"; TURQ <- "#00afc0"; ESC <- "#040e19"; LARANJA <- "#b5541c"; CINZA <- "#747474"

interp <- function(...) div(class = "interp", tags$span(class = "t", "Como ler"), ...)
figura <- function(num, titulo, ...) card(card_header(tags$span(class = "fn", paste("Figura", num)), tags$strong(titulo)), ...)
AVISO <- "Associação estatística em dados agregados por dia; não prova que o calor causou cada óbito."

tema <- bs_theme(version = 5, primary = AZUL, secondary = TURQ, bg = "#f7f7f7", fg = ESC, base_font = font_google("Inter", local = FALSE))
css <- "
.navbar{background:#040e19!important;border-bottom:3px solid #00afc0}.navbar .nav-link,.navbar-brand{color:#eef1f4!important}
.navbar .nav-link.active{color:#fff!important;font-weight:600;border-bottom:3px solid #00afc0}
.fn{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#008fa0;font-weight:700}
.interp{background:#f0f4f7;border-left:3px solid #00afc0;padding:9px 13px;margin-top:12px;font-size:14px}
.interp .t{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#5f6770;font-weight:700}
.nota{font-size:12px;color:#5f6770;margin-top:8px}.card{border-radius:4px}
table.mt{border-collapse:collapse;font-size:13px;margin:8px 0}table.mt th,table.mt td{border-bottom:1px solid #d6d6d6;padding:4px 10px;text-align:left}
table.mt th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:#5f6770}"

controles <- function(id, defs = TRUE, faixa = TRUE, local = TRUE, periodo = TRUE) {
  tagList(
    selectInput(paste0(id, "_pop"), "População de óbitos", POPS, width = "100%"),
    if (local) selectInput(paste0(id, "_loc"), "Local do óbito", LOCAIS, width = "100%"),
    if (faixa) selectInput(paste0(id, "_fx"), "Faixa etária", FAIXAS, width = "100%"),
    if (defs) selectInput(paste0(id, "_def"), "Definição de calor", DEFS, selected = DEFS[1], width = "100%"),
    if (periodo) selectInput(paste0(id, "_per"), "Período", PERIODOS, width = "100%"))
}

tabela_html <- function(df) {
  cab <- paste0("<tr>", paste0("<th>", names(df), "</th>", collapse = ""), "</tr>")
  lin <- apply(df, 1, function(r) paste0("<tr>", paste0("<td>", r, "</td>", collapse = ""), "</tr>"))
  HTML(paste0("<table class='mt'>", cab, paste(lin, collapse = ""), "</table>"))
}

ui <- page_navbar(title = "Mortalidade e calor, Rio de Janeiro", theme = tema, bg = ESC, inverse = TRUE, header = tags$head(tags$style(HTML(css))), fillable = FALSE,
  nav_panel("Série semanal", layout_sidebar(sidebar = sidebar(width = 300, controles("s", defs = FALSE, periodo = FALSE),
      selectInput("s_crit", "Sombrear semanas com", c("Índice de calor máx. ≥ 36 °C em ≥ 3 dias" = "ic", "Algum dia com anomalia térmica (z ≥ 1,96)" = "an", "Nada" = "no"))),
    figura(1, "Óbitos semanais por causas naturais: observados, esperados e faixa de 95%", plotlyOutput("s_plot", height = 430), uiOutput("s_interp")))),
  nav_panel("Horas de calor × RR", layout_sidebar(sidebar = sidebar(width = 300, controles("h", defs = FALSE),
      radioButtons("h_modo", "Mostrar", c("Todas as células" = "rr", "Só células com IC 95% que exclui 1" = "sig"))),
    figura(2, "RR em dias com ao menos H horas de índice de calor ≥ K °C (lag 0–3)", plotlyOutput("h_plot", height = 480), uiOutput("h_interp")))),
  nav_panel("RR por faixa, local e defasagem", layout_sidebar(sidebar = sidebar(width = 300, selectInput("r_pop", "População de óbitos", POPS),
      selectInput("r_def", "Definição de calor", DEFS, selected = DEFS[1]),
      selectInput("r_esq", "Efeito", c("Dia de calor (lag 0–3)" = "dia", "Isolado × onda de calor" = "onda")), uiOutput("r_termo_ui"),
      selectInput("r_per", "Período", PERIODOS), selectInput("r_fx", "Faixa para o detalhe", FAIXAS)),
    layout_columns(col_widths = c(7, 5),
      figura(3, "RR por faixa etária e local", plotlyOutput("r_hm", height = 520), uiOutput("r_interp")),
      figura("3b", "Detalhe por local na faixa selecionada", plotlyOutput("r_fo", height = 420), uiOutput("r_interp2"))),
    figura(4, "RR por defasagem (dias após o evento) e acumulado", selectInput("l_loc", "Local do óbito", LOCAIS), plotlyOutput("l_plot", height = 360), uiOutput("l_interp")))),
  nav_panel("CIDs em dias de calor", layout_sidebar(sidebar = sidebar(width = 300, controles("k", faixa = FALSE),
      selectInput("k_fx", "Faixa etária", c("Todas as idades", "61+")),
      selectInput("k_esq", "Efeito", c(setNames(paste0("dia|", T_DIA), T_DIA), setNames(paste0("onda|", T_ONDA), T_ONDA), setNames(paste0("onda|", T_ISO), T_ISO))),
      checkboxInput("k_todos", "Incluir causas sem diferença do esperado", FALSE), checkboxInput("k_inf", "Só causas da lista a priori sensível ao calor", FALSE),
      checkboxInput("k_nat", "Só causas naturais (A00–R99)", FALSE)),
    figura(5, "Causas (CID-10, 3 caracteres) com RR diferente do esperado em dias de calor", plotlyOutput("k_plot", height = 520), uiOutput("k_interp")),
    figura("5b", "Óbitos semanais da causa selecionada", selectInput("k_cid", "Causa", NULL, width = "100%"), plotlyOutput("k_ser", height = 340), uiOutput("k_interp2")))),
  nav_panel("Unidades e bairros", layout_sidebar(sidebar = sidebar(width = 300, selectInput("u_pop", "População de óbitos", POPS),
      selectInput("u_def", "Definição de calor", DEFS, selected = DEFS[1]),
      selectInput("u_tipo", "Tipo de unidade", c("Todas", "Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde")),
      sliderInput("u_jan", "Período do mapa", min = min(clima$dia), max = max(clima$dia), value = range(clima$dia), timeFormat = "%d/%m/%Y", width = "100%")),
    figura(6, "RR por unidade de saúde no período selecionado", if (requireNamespace("leaflet", quietly = TRUE)) leafletOutput("u_map", height = 520) else div("Instale o pacote leaflet para ver o mapa."), uiOutput("u_interp")),
    figura(7, "RR por bairro da unidade, período completo (25 maiores)", DTOutput("u_tab"), uiOutput("u_interp2")))),
  nav_panel("Clima e exposição", layout_sidebar(sidebar = sidebar(width = 300, selectInput("c_var", "Variável", c("Temperatura média" = "t_med", "Índice de calor médio" = "hi_med")),
      dateRangeInput("c_dat", "Período", start = max(clima$dia) - 365 * 2, end = max(clima$dia), min = min(clima$dia), max = max(clima$dia), format = "dd/mm/yyyy")),
    figura(8, "Temperatura e índice de calor diários: observado, esperado e anomalia", plotlyOutput("c_plot", height = 430), uiOutput("c_interp")),
    figura(9, "Percentual de dias de exposição por ano", plotlyOutput("a_plot", height = 330), uiOutput("a_interp")))),
  nav_panel("Métodos e fontes", card(uiOutput("metodos"))))

server <- function(input, output, session) {
  # ---------- Série semanal ----------
  sdat <- reactive(serie |> filter(pop == input$s_pop, local == input$s_loc, faixa == input$s_fx) |> left_join(semanas |> select(ini, nb, na, cov, inc), by = "ini"))
  output$s_plot <- renderPlotly({
    d <- sdat(); validate(need(nrow(d) > 0, "Menos de 300 óbitos nesta combinação."))
    calor <- switch(input$s_crit, ic = d$nb >= 3, an = d$na >= 1, rep(FALSE, nrow(d)))
    d <- d |> mutate(obs = ifelse(inc, NA, obs), seg = cumsum(is.na(esp))); dd <- d |> filter(!is.na(esp))     # semanas fora do ajuste: sem esperado e sem faixa (trechos separados)
    p <- ggplot(d, aes(ini)) + geom_ribbon(data = dd, aes(ymin = lo, ymax = up, group = seg), fill = AZUL, alpha = .15) + geom_line(aes(y = obs), color = CINZA, linewidth = .4) +
      geom_line(data = dd, aes(y = esp, group = seg), color = AZUL, linewidth = .8) + (if (any(d$obs > d$up & !d$cov & !d$inc, na.rm = TRUE)) geom_point(data = d[which(d$obs > d$up & !d$cov & !d$inc), ], aes(y = obs), size = 1.3)) +
      (if (any(calor)) geom_rect(data = d[which(calor), ], aes(xmin = ini, xmax = ini + 7, ymin = -Inf, ymax = Inf), fill = LARANJA, alpha = .22, inherit.aes = FALSE)) +
      (if (any(d$cov)) geom_rect(data = d[which(d$cov), ], aes(xmin = ini, xmax = ini + 7, ymin = -Inf, ymax = Inf), fill = CINZA, alpha = .18, inherit.aes = FALSE)) +
      labs(x = NULL, y = "Óbitos por semana") + theme_minimal(base_size = 12)
    ggplotly(p)
  })
  output$s_interp <- renderUI({
    d <- sdat() |> filter(!cov, !inc, !is.na(esp))
    if (!nrow(d)) return(NULL)
    base <- sprintf("Linha azul: óbitos esperados pelo modelo de tendência e sazonalidade (spline de 7 graus de liberdade por ano), sem usar o clima. Faixa: esperado ± 1,96·√(φ·esperado). Semanas do período COVID e de meses com registro incompleto ficam fora do ajuste. Se o modelo estiver bem calibrado, cerca de 2,5%% das semanas ficam acima do limite superior: aqui, %s.", pct(mean(d$obs > d$up)))
    if (input$s_crit == "no") return(interp(base))
    calor <- if (input$s_crit == "ic") d$nb >= 3 else d$na >= 1
    H <- d[calor, ]; N <- d[!calor, ]
    interp(HTML(sprintf("%s<br>Em <b>%d</b> semanas de calor os óbitos somaram <b>%s</b> contra <b>%s</b> esperados (O/E <b>%s</b>); nas outras <b>%d</b> semanas, O/E <b>%s</b>. Semanas acima do limite: %s entre as de calor e %s entre as demais. Esta é uma comparação descritiva: como o calor se concentra no verão, qualquer falha do modelo em captar a sazonalidade aparece aqui como falso efeito. A estimativa ajustada por dia está nas Figuras 3 a 5. %s",
      base, nrow(H), fn(sum(H$obs)), fn(sum(H$esp)), if (nrow(H)) fr(sum(H$obs) / sum(H$esp)) else "–", nrow(N), fr(sum(N$obs) / sum(N$esp)),
      if (nrow(H)) pct(mean(H$obs > H$up)) else "–", pct(mean(N$obs > N$up)), AVISO)))
  })
  # ---------- Horas x RR ----------
  hdat <- reactive(heat |> filter(pop == input$h_pop, local == input$h_loc, faixa == input$h_fx, periodo == input$h_per))
  output$h_plot <- renderPlotly({
    d <- hdat(); validate(need(nrow(d) > 0, "Sem estimativa para esta combinação (poucos óbitos ou poucos dias expostos)."))
    d <- d |> mutate(sig = lo > 1 | hi < 1, v = if (input$h_modo == "sig") ifelse(sig, rr, NA) else rr,
      txt = sprintf("Índice de calor ≥ %s °C por ≥ %s h/dia\nRR %s\n%s dias expostos · %s óbitos", limiar, horas, frci(rr, lo, hi), fn(dias_expostos), fn(n)))
    g <- ggplot(d, aes(factor(limiar), factor(horas), fill = v, text = txt)) + geom_tile(color = "white") +
      geom_text(aes(label = fr(rr), fontface = ifelse(sig, "bold", "plain")), size = 3, na.rm = TRUE) +
      scale_fill_gradient2(low = AZUL, mid = "#f7f7f7", high = LARANJA, midpoint = 1, na.value = "#ececec", name = "RR") +
      labs(x = "Índice de calor ≥ K (°C)", y = "Mínimo de horas no dia (H)") + theme_minimal(base_size = 12)
    ggplotly(g, tooltip = "text")
  })
  output$h_interp <- renderUI({
    d <- hdat(); if (!nrow(d)) return(NULL)
    s <- d |> filter(lo > 1); b <- d |> filter(hi < 1); mx <- d[which.max(d$rr), ]
    esperado <- 0.05 * nrow(d) / 2
    interp(HTML(sprintf("Cada célula é um modelo separado: compara os óbitos nos dias com ao menos <b>H</b> horas de índice de calor ≥ <b>K</b> °C (e nos três dias seguintes) com o esperado sem esse calor. As células se sobrepõem (um dia com 6 h ≥ 36 °C também conta em 1 h ≥ 32 °C), portanto não são independentes e <b>não há correção para comparações múltiplas</b>. Das <b>%d</b> células, <b>%d</b> têm RR &gt; 1 com IC 95%% acima de 1 e <b>%d</b> têm RR &lt; 1; só por acaso, esperar-se-iam cerca de %s de cada lado. Maior RR: <b>%s</b> com K = %d °C e H = %d h (%s dias expostos), que é o máximo entre as células e por isso tende a superestimar o efeito (maldição do vencedor). Leia o padrão do conjunto, não uma célula isolada. %s",
      nrow(d), nrow(s), nrow(b), fr(esperado, 1), frci(mx$rr, mx$lo, mx$hi), mx$limiar, mx$horas, fn(mx$dias_expostos), AVISO)))
  })
  # ---------- RR por faixa e local ----------
  output$r_termo_ui <- renderUI(if (input$r_esq == "onda") selectInput("r_termo", "Termo", c(T_ONDA, T_ISO)))
  rdat <- reactive({
    t <- if (input$r_esq == "dia") T_DIA else (input$r_termo %||% T_ONDA)
    rr_lf |> filter(pop == input$r_pop, definicao == input$r_def, esquema == input$r_esq, periodo == input$r_per, termo == t, local != "Ignorado")
  })
  output$r_hm <- renderPlotly({
    d <- rdat(); validate(need(nrow(d) > 0, "Sem estimativa."))
    d <- d |> mutate(sig = lo > 1 | hi < 1, txt = sprintf("%s · %s\nRR %s\n%s óbitos · %s dias expostos", faixa, local, frci(rr, lo, hi), fn(n), fn(dias_expostos)), faixa = factor(faixa, rev(FAIXAS)), local = factor(local, LOCAIS))
    g <- ggplot(d, aes(local, faixa, fill = rr, text = txt)) + geom_tile(color = "white") + geom_text(aes(label = fr(rr), fontface = ifelse(sig, "bold", "plain")), size = 3) +
      scale_fill_gradient2(low = AZUL, mid = "#f7f7f7", high = LARANJA, midpoint = 1, name = "RR") + labs(x = NULL, y = NULL) + theme_minimal(base_size = 11) + theme(axis.text.x = element_text(angle = 30, hjust = 1))
    ggplotly(g, tooltip = "text")
  })
  output$r_interp <- renderUI({
    d <- rdat(); if (!nrow(d)) return(NULL); up <- d |> filter(lo > 1) |> arrange(desc(rr)); dn <- d |> filter(hi < 1)
    interp(HTML(sprintf("Cada célula é um modelo (quase-Poisson, spline de tempo, dia da semana; erro-padrão robusto à autocorrelação). Das <b>%d</b> combinações, <b>%d</b> têm RR &gt; 1 com IC 95%% acima de 1 e <b>%d</b> têm RR &lt; 1. Sem nenhum efeito, esperam-se cerca de %s células de cada lado só por acaso (5%% de erro tipo I, sem correção). %s RR perto de 1 com IC largo (poucos óbitos) é inconclusivo, não ausência de efeito. %s",
      nrow(d), nrow(up), nrow(dn), fr(0.025 * nrow(d), 1),
      if (nrow(up)) sprintf("Maior RR: <b>%s</b> em <b>%s</b>, faixa <b>%s</b>, isto é, %s%% mais óbitos nos dias expostos do que o esperado sem o evento.", frci(up$rr[1], up$lo[1], up$hi[1]), up$local[1], up$faixa[1], fr((up$rr[1] - 1) * 100, 1)) else "Nenhuma combinação com RR acima de 1 e IC que exclua 1.", AVISO)))
  })
  output$r_fo <- renderPlotly({
    d <- rdat() |> filter(faixa == input$r_fx) |> mutate(local = factor(local, rev(LOCAIS))); validate(need(nrow(d) > 0, "Menos de 300 óbitos nesta faixa."))
    g <- ggplot(d, aes(rr, local, text = sprintf("%s\nRR %s", local, frci(rr, lo, hi)))) + geom_vline(xintercept = 1, color = CINZA) +
      geom_segment(aes(x = lo, xend = hi, y = local, yend = local, color = lo > 1 | hi < 1)) + geom_point(aes(color = lo > 1 | hi < 1)) +
      scale_color_manual(values = c(`TRUE` = LARANJA, `FALSE` = CINZA), guide = "none") + labs(x = "RR (IC 95%)", y = NULL) + theme_minimal(base_size = 12)
    ggplotly(g, tooltip = "text") |> layout(showlegend = FALSE)
  })
  output$r_interp2 <- renderUI({
    d <- rdat() |> filter(faixa == input$r_fx, lo > 1)
    interp(HTML(if (nrow(d)) sprintf("Faixa <b>%s</b>: RR acima de 1 em %s. Nos demais locais o IC inclui 1 ou há poucos óbitos.", input$r_fx, paste(sprintf("<b>%s</b> (%s; %s–%s)", d$local, fr(d$rr), fr(d$lo), fr(d$hi)), collapse = ", ")) else sprintf("Faixa <b>%s</b>: nenhum local com RR significativamente acima de 1.", input$r_fx)))
  })
  # ---------- Defasagem ----------
  ldat <- reactive(lagtab |> filter(pop == input$r_pop, local == input$l_loc, faixa == input$r_fx, periodo == input$r_per, definicao == input$r_def))
  output$l_plot <- renderPlotly({
    d <- ldat(); validate(need(nrow(d) > 0, "Sem estimativa para esta combinação."))
    d <- d |> mutate(termo = factor(termo, LAGS), txt = sprintf("%s\nRR %s", termo, frci(rr, lo, hi)), grupo = ifelse(grepl("^cum", as.character(termo)), "Acumulado", "Por dia"))
    g <- ggplot(d, aes(termo, rr, text = txt)) + geom_hline(yintercept = 1, color = CINZA) + geom_segment(aes(x = termo, xend = termo, y = lo, yend = hi, color = grupo)) +
      geom_point(aes(color = grupo)) + scale_color_manual(values = c(`Por dia` = AZUL, Acumulado = LARANJA), name = NULL) +
      labs(x = "Dia após o evento (lag 0 = mesmo dia) · cum01, cum03, cum07 = efeito acumulado nos lags 0–1, 0–3 e 0–7", y = "RR (IC 95%)") + theme_minimal(base_size = 11)
    ggplotly(g, tooltip = "text")
  })
  output$l_interp <- renderUI({
    d <- ldat(); if (!nrow(d)) return(NULL); a <- function(k) d[d$termo == k, ]
    interp(HTML(sprintf("Todos os lags 0 a 7 entram juntos em um só modelo; cada ponto é o efeito do evento naquele dia, descontado dos demais. O acumulado é o efeito combinado (soma dos coeficientes, não a média dos RR). Acumulado lag 0–3, que corresponde à janela usada nas outras figuras: <b>%s</b>; lag 0–7: <b>%s</b>. Se o RR de um lag fica abaixo de 1 depois de um pico, pode ser antecipação de óbitos (&quot;deslocamento da colheita&quot;), e não proteção. Lags vizinhos são correlacionados; interpretar o conjunto. %s",
      if (nrow(a("cum03"))) frci(a("cum03")$rr, a("cum03")$lo, a("cum03")$hi) else "–", if (nrow(a("cum07"))) frci(a("cum07")$rr, a("cum07")$lo, a("cum07")$hi) else "–", AVISO)))
  })
  # ---------- CIDs ----------
  kdat <- reactive({
    sp <- strsplit(input$k_esq, "|", fixed = TRUE)[[1]]
    cid_rr |> filter(pop == input$k_pop, local == input$k_loc, faixa == input$k_fx, periodo == input$k_per, definicao == input$k_def, esquema == sp[1], termo == sp[2],
                     !input$k_inf | sensivel, !input$k_nat | natural) |> left_join(cid_nm, by = "cid")
  })
  observe({
    d <- kdat() |> filter(q < .05) |> arrange(desc(rr)); ch <- cid_sem |> filter(pop == input$k_pop, local == input$k_loc) |> distinct(cid) |> left_join(cid_nm, by = "cid")
    updateSelectInput(session, "k_cid", choices = setNames(ch$cid, paste(ch$cid, ch$nome, sep = " · ")), selected = if (nrow(d) && d$cid[1] %in% ch$cid) d$cid[1] else ch$cid[1])
  })
  output$k_plot <- renderPlotly({
    d <- kdat(); d <- if (input$k_todos) d else d |> filter(q < .05); validate(need(nrow(d) > 0, "Nenhuma causa difere do esperado com esta combinação."))
    d <- d |> mutate(rotulo = paste(cid, substr(nome, 1, 50)), cor = ifelse(q >= .05, "ns", ifelse(rr > 1, "up", "dn")),
                     txt = sprintf("%s %s\nRR %s\nq = %s · %s óbitos no total", cid, nome, frci(rr, lo, hi), fr(q, 3), fn(n)))
    g <- ggplot(d, aes(rr, reorder(rotulo, rr), text = txt)) + geom_vline(xintercept = 1, color = CINZA) + geom_segment(aes(x = lo, xend = hi, y = reorder(rotulo, rr), yend = reorder(rotulo, rr), color = cor)) +
      geom_point(aes(color = cor)) + scale_color_manual(values = c(up = LARANJA, dn = AZUL, ns = CINZA), guide = "none") + labs(x = "RR (IC 95%)", y = NULL) + theme_minimal(base_size = 11)
    ggplotly(g, tooltip = "text") |> layout(showlegend = FALSE)
  })
  output$k_interp <- renderUI({
    d <- kdat(); sg <- d |> filter(q < .05); up <- sg |> filter(rr > 1) |> arrange(desc(rr)); dw <- sg |> filter(rr < 1)
    interp(HTML(sprintf("%d causas com ao menos 1.500 óbitos foram avaliadas; <b>%d</b> diferem do esperado após correção de Benjamini–Hochberg (taxa de falsas descobertas q &lt; 0,05, calculada dentro desta combinação de filtros). %s %s Associação estatística; uma causa com RR &gt; 1 pode refletir o grupo etário que a compõe, e RR &lt; 1 pode ser antecipação de óbitos ou mudança de registro. %s",
      nrow(d), nrow(sg), if (nrow(up)) sprintf("RR acima de 1: %s.", paste(sprintf("<b>%s</b> %s (RR %s; %s–%s)", head(up$cid, 4), head(up$nome, 4), fr(head(up$rr, 4)), fr(head(up$lo, 4)), fr(head(up$hi, 4))), collapse = "; ")) else "Nenhuma causa com RR significativamente acima de 1.",
      if (nrow(dw)) sprintf("RR abaixo de 1 em %d causa(s).", nrow(dw)) else "", AVISO)))
  })
  output$k_ser <- renderPlotly({
    d <- cid_sem |> filter(pop == input$k_pop, local == input$k_loc, cid == input$k_cid); validate(need(nrow(d) > 0, "Série não estimada (menos de 1.500 óbitos)."))
    d <- d |> left_join(semanas |> select(ini, inc), by = "ini") |> mutate(obs = ifelse(inc, NA, obs), seg = cumsum(is.na(esp))); dd <- d |> filter(!is.na(esp))
    g <- ggplot(d, aes(ini)) + geom_line(aes(y = obs), color = CINZA, linewidth = .4) + geom_line(data = dd, aes(y = esp, group = seg), color = AZUL, linewidth = .8) + geom_line(data = dd, aes(y = up, group = seg), color = AZUL, linetype = 2, alpha = .5) + labs(x = NULL, y = "Óbitos por semana") + theme_minimal(base_size = 12)
    ggplotly(g)
  })
  output$k_interp2 <- renderUI({
    d <- cid_sem |> filter(pop == input$k_pop, local == input$k_loc, cid == input$k_cid) |> left_join(semanas |> select(ini, nb, cov, inc), by = "ini") |> filter(!cov, !inc, !is.na(esp)); if (!nrow(d)) return(NULL)
    H <- d |> filter(nb >= 3); N <- d |> filter(nb < 3)
    interp(HTML(sprintf("Em <b>%d</b> semanas com ao menos 3 dias de índice de calor ≥ 36 °C (fora do COVID e de meses incompletos), os óbitos por esta causa somaram <b>%s</b> contra <b>%s</b> esperados (O/E <b>%s</b>); nas outras <b>%d</b> semanas, <b>%s</b>. Descritivo; o RR ajustado por dia está na Figura 5.",
      nrow(H), fn(sum(H$obs)), fn(sum(H$esp)), if (nrow(H)) fr(sum(H$obs) / sum(H$esp)) else "–", nrow(N), fr(sum(N$obs) / sum(N$esp)))))
  })
  # ---------- Unidades ----------
  ujan <- reactive({
    d <- unid_j |> filter(pop == input$u_pop, definicao == input$u_def, dia >= input$u_jan[1], dia <= input$u_jan[2]) |>
      group_by(cnes) |> summarise(O = sum(obs), E = sum(esp), phi = first(phi), nd = n(), .groups = "drop") |> filter(O >= 20, E > 0) |>
      mutate(rr = O / E, lo = rr * exp(-1.96 * sqrt(phi / O)), hi = rr * exp(1.96 * sqrt(phi / O)))
    unid |> filter(pop == input$u_pop, !is.na(lat), input$u_tipo == "Todas" | tipo == input$u_tipo) |> left_join(d, by = c("cnes"))
  })
  if (requireNamespace("leaflet", quietly = TRUE)) output$u_map <- renderLeaflet({
    d <- ujan()
    leaflet(d) |> addProviderTiles("CartoDB.Positron") |> addCircleMarkers(~lon, ~lat, radius = ~3 + sqrt(n) * .1, color = ~ifelse(is.na(rr), CINZA, ifelse(lo > 1, LARANJA, CINZA)), fillOpacity = ~ifelse(is.na(rr), 0, .75), weight = 1.5,
      popup = ~sprintf("<b>%s</b><br>%s · %s<br>%s óbitos<br>%s", nome, bairro, tipo, fn(n), ifelse(is.na(rr), paste0("sem estimativa: ", ifelse(is.na(motivo), "poucos óbitos na janela", motivo)), paste("RR", frci(rr, lo, hi)))))
  })
  output$u_interp <- renderUI({
    d <- ujan() |> filter(!is.na(rr))
    interp(HTML(sprintf("Só entram unidades com série estável (operaram por ao menos 4 anos, com óbitos em 90%% dos meses, sem os 90 dias de abertura ou fechamento) e ao menos 1.500 óbitos. Neste período (%s a %s), <b>%d</b> das <b>%d</b> unidades têm ao menos 20 óbitos nos dias expostos. RR = óbitos observados nesses dias ÷ esperados sem o evento, pelo modelo ajustado uma vez para todo o período de operação da unidade. IC 95%% aproximado: RR·exp(±1,96·√(φ/O)). Em <b>%d</b> o IC fica acima de 1 e em <b>%d</b> abaixo de 1. Com tantas unidades, algumas saem acima de 1 por acaso. O RR descreve os óbitos <i>registrados na unidade</i> e depende também do fluxo de pacientes; não mede o risco da população do bairro.",
      dt(input$u_jan[1]), dt(input$u_jan[2]), nrow(d), nrow(ujan()), sum(d$lo > 1), sum(d$hi < 1))))
  })
  output$u_tab <- renderDT({
    b <- bairros |> filter(pop == input$u_pop, (definicao == input$u_def) | is.na(definicao)) |> arrange(desc(n)) |> head(25) |>
      transmute(Bairro = tools::toTitleCase(tolower(bairro)), `Óbitos` = n, Unidades = unidades, `Óbitos em unidades estáveis` = n_rr, RR = round(rr, 2), `IC 95%` = ifelse(is.na(rr), "–", paste0(fr(lo), " a ", fr(hi))))
    datatable(b, rownames = FALSE, options = list(dom = "t", pageLength = 25))
  })
  output$u_interp2 <- renderUI(interp("Bairro do estabelecimento, não da residência. O RR do bairro só é calculado a partir de unidades estáveis, com ao menos 3.000 óbitos nelas; “–” = não estimado."))
  # ---------- Clima ----------
  output$c_plot <- renderPlotly({
    v <- input$c_var; d <- clima |> filter(dia >= input$c_dat[1], dia <= input$c_dat[2]); o <- d[[paste0(v, "_o")]]; e <- d[[paste0(v, "_e")]]; sd <- d[[paste0(v, "_sd")]]; z <- d[[paste0(v, "_z")]]
    p <- ggplot(data.frame(dia = d$dia, o, e, lo = e - 1.96 * sd, up = e + 1.96 * sd, z), aes(dia)) + geom_ribbon(aes(ymin = lo, ymax = up), fill = AZUL, alpha = .15) + geom_line(aes(y = o), color = CINZA, linewidth = .3) +
      geom_line(aes(y = e), color = AZUL, linewidth = .8) + geom_point(data = ~ filter(.x, z >= 1.96), aes(y = o), color = LARANJA, size = 1.4) + labs(x = NULL, y = "°C") + theme_minimal(base_size = 12)
    ggplotly(p)
  })
  output$c_interp <- renderUI({
    v <- input$c_var; d <- clima |> filter(dia >= input$c_dat[1], dia <= input$c_dat[2]); z <- d[[paste0(v, "_z")]]; g <- gam |> filter(variavel == v)
    interp(HTML(sprintf("No recorte, <b>%d</b> de %d dias (%s%%) tiveram anomalia z ≥ 1,96, isto é, ficaram acima do limite superior de 95%% do esperado para a data. A tendência de longo prazo estimada é de <b>+%s °C por década</b> (IC 95%%: %s a %s; a incerteza da tendência vem de um modelo que assume erros independentes e é otimista). Estes dias definem a exposição “anomalia térmica” nas demais abas.",
      sum(z >= 1.96, na.rm = TRUE), nrow(d), fr(100 * mean(z >= 1.96, na.rm = TRUE), 1), fr(g$tendencia, 1), fr(g$ic_inf, 1), fr(g$ic_sup, 1))))
  })
  output$a_plot <- renderPlotly({
    d <- anual |> select(ano, `Índice de calor máx. ≥ 36 °C` = pct_ic, `Anomalia térmica z ≥ 1,96` = pct_an) |> pivot_longer(-ano, names_to = "criterio", values_to = "pct")
    g <- ggplot(d, aes(ano, pct, color = criterio)) + geom_line() + geom_point() + scale_color_manual(values = c(AZUL, LARANJA), name = NULL) + labs(x = NULL, y = "% dos dias") + theme_minimal(base_size = 12)
    ggplotly(g)
  })
  output$a_interp <- renderUI(interp(HTML("O limiar absoluto (índice de calor ≥ 36 °C) é atingido em uma fração crescente dos dias, em parte pelo aquecimento e em parte porque a rede de estações mudou ao longo do tempo (menos estações e outras localizações em alguns anos). A anomalia (z) corrige a tendência de longo prazo e, por isso, se distribui de forma mais estável entre os anos. Nenhuma das duas definições é neutra: cada uma muda <i>quais</i> dias entram na comparação.")))
  # ---------- Métodos ----------
  output$metodos <- renderUI({
    f <- met$fluxo; ex <- met$exemplo; ex1 <- ex[[length(ex)]]
    sens <- met$sens |> filter(grupo %in% c("Principal", "Incerteza", "Controle de tempo", "Período")) |> transmute(Definição = definicao, Especificação = spec, RR = fr(rr, 3), `IC 95%` = paste0(fr(lo, 3), " a ", fr(hi, 3)))
    diag <- met$diag |> transmute(`gl/ano` = df_ano, `φ` = fr(phi, 2), `ACF lag 1` = fr(acf1, 2), `ACF lag 7` = fr(acf7, 2), `EP robusto ÷ EP quase-Poisson` = fr(razao_ep, 2))
    fluxo <- data.frame(Etapa = c("Óbitos ocorridos no município", "… residentes no Rio", "… causas naturais (A00–R99, sem COVID-19): desfecho principal", "… causas externas (V–Y)", "… COVID-19 (B34), fora de todas as análises", "Dias no período", "Dias no modelo “Sem COVID” (padrão)", "Dias no modelo “Todo o período”"),
      `Óbitos / dias` = c(fn(f$obitos_ocorridos), fn(f$obitos_residentes), fn(f$obitos_res_naturais), fn(f$obitos_res_externos), fn(f$obitos_res_covid), fn(f$n_dias), fn(f$dias_modelo_sem_covid), fn(f$dias_modelo_todo)), check.names = FALSE)
    tagList(
      h4("Métodos e fontes"),
      p("O painel HTML traz o texto completo (pergunta e desenho, hipóteses H0 a H9, fluxo de dados, fórmula do modelo, passo a passo do cálculo de um RR, limitações e referências). Aqui estão o resumo e os números que o sustentam: ",
        tags$a(href = HTML_PAINEL, target = "_blank", "abrir o painel HTML"), "."),
      h5("Desenho"), p("Série temporal ecológica diária (óbitos por causas naturais no município do Rio de Janeiro, 2012 em diante). Modelo quase-Poisson com log do número esperado de óbitos = spline natural do tempo (7 graus de liberdade por ano) + dia da semana + exposição ao calor. Exposição = dia com evento de calor em t, t−1, t−2 ou t−3. RR = exp(β). Erro-padrão robusto de Newey–West (14 lags), porque os resíduos têm autocorrelação. Período COVID (mar/2020 a jun/2022), meses com registro incompleto no SIM e dias sem clima ficam fora do ajuste."),
      h5("Fluxo de dados"), tabela_html(fluxo),
      h5("Exemplo de cálculo (último critério de calor)"),
      p(sprintf("%s dias no modelo, %s dias expostos (%s%%). Observados nos dias expostos: %s; esperados sem exposição: %s; O/E = %s = RR. β = %s, EP robusto = %s, IC 95%% = %s a %s.",
        fn(ex1$n_dias), fn(ex1$dias_expostos), fr(ex1$pct_expostos, 1), fn(ex1$obs_expostos), fn(ex1$esp_sem_exposicao), fr(ex1$obs_esp, 3), fr(ex1$beta, 4), fr(ex1$ep_hac, 4), fr(ex1$lo, 3), fr(ex1$hi, 3))),
      h5("Diagnóstico: autocorrelação dos resíduos e controle de tempo"), tabela_html(diag),
      p(class = "nota", "Com poucos graus de liberdade por ano a tendência e a sazonalidade ficam mal captadas, os resíduos mantêm autocorrelação e o EP de quase-Poisson subestima a incerteza (razão entre os EP). Por isso o modelo usa 7 gl/ano e EP robusto."),
      h5("Sensibilidade do RR a escolhas do desenho"), tabela_html(sens),
      h5("Principais limitações"),
      tags$ul(tags$li("Dado agregado por dia: não se conhece a exposição individual (falácia ecológica); o efeito é do conjunto da população."),
              tags$li("Clima médio do município, sem variação entre bairros; erro de classificação da exposição."),
              tags$li("Confundimento residual por poluição do ar, influenza e outros vírus respiratórios, feriados e eventos."),
              tags$li("Duas definições de calor, janela de 4 dias e vários recortes: muitas comparações; o FDR só é aplicado entre causas."),
              tags$li("O limiar absoluto muda de significado ao longo do tempo (aquecimento e mudança da rede de estações)."),
              tags$li("Causa básica do SIM tem qualidade variável; mudanças de registro entre anos podem aparecer como efeito."),
              tags$li("RR &lt; 1 em alguns subgrupos pode ser antecipação de óbitos; este desenho não separa as duas explicações.")),
      p(class = "nota", sprintf("Tabelas geradas em %s. Fontes: SIM (DATASUS) via Release sim-mrj; clima INMET e Alerta Rio, HAAT, via Release clima-mrj; código no repositório.", meta$gerado_em)))
  })
}
shinyApp(ui, server)
