# Painel Shiny: Figura 1 (óbitos observados x esperados sem calor), com os modelos ajustados quando o recorte é escolhido.
#
# Os dados vêm do cache preparado por shiny/atualizar_cache.R (SIM e HAAT das Releases do GitHub). Ao abrir, a página recebe só o calendário e o clima.
# Cada combinação de local, faixa etária, raça/cor e medida de calor é ajustada sob demanda (R/servico.R) em processos separados e guardada em disco.
#
# Variáveis de ambiente (todas opcionais):
#   PAINEL_RAIZ           pasta do projeto (padrão: a pasta acima deste app)
#   PAINEL_CACHE          pasta do cache (padrão: <projeto>/shiny/cache)
#   PAINEL_TRABALHADORES  quantos modelos podem ser ajustados ao mesmo tempo (padrão: 2; cada trabalhador usa cerca de 300 MB)

invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
library(shiny)

raiz <- normalizePath(Sys.getenv("PAINEL_RAIZ", file.path(getwd(), "..")), mustWork = TRUE)
if (!file.exists(file.path(raiz, "R", "funcoes.R")))
  stop("Não achei o projeto em ", raiz, ". Defina a variável de ambiente PAINEL_RAIZ com a pasta painel_quarto.")
pasta <- Sys.getenv("PAINEL_CACHE", file.path(raiz, "shiny", "cache"))
n_trab <- max(1L, suppressWarnings(as.integer(Sys.getenv("PAINEL_TRABALHADORES", "2"))), na.rm = TRUE)

source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "metodos.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))

future::plan("multisession", workers = n_trab)
addResourcePath("painel", file.path(raiz, "assets"))

ROTULO_POP <- c(res = "Residentes no Rio que morreram no Rio", todos = "Todos os óbitos ocorridos no Rio")

# ---------------------------------------------------------------- dados-base de cada população (calculados uma vez por versão dos dados)
.base <- new.env()

pops_prontas <- function() names(ROTULO_POP)[vapply(names(ROTULO_POP), function(p) !is.null(meta_cache(pasta, p)), TRUE)]

# Lê o cache, monta o que a página precisa (calendário, clima, texto dos métodos) e libera o contexto grande da memória deste processo.
base_info <- function(pop) {
  m <- meta_cache(pasta, pop)
  if (is.null(m)) return(NULL)
  b <- .base[[pop]]
  if (!is.null(b) && identical(b$chave, m$chave)) return(b)
  P <- obter_P(pasta, pop)
  if (is.null(P)) return(NULL)
  elig <- obter_elegibilidade(pasta, pop, P)
  base <- base_sob_demanda(P, elig)
  M <- jsonlite::fromJSON(json_utf8(base$meta), simplifyVector = TRUE)             # mesma forma que o Quarto lê do resumo
  b <- list(chave = P$chave, elegiveis = elig,
            json_base = json_utf8(base), json_troca = json_utf8(list(meta = base$meta, rc = base$rc, rcs = base$rcs)),
            metodos = texto_metodos(M, sum(is.na(P$cx$d$idade_anos)), NULL, base$meta$dados))
  if (exists(pop, envir = .servico, inherits = FALSE)) rm(list = pop, envir = .servico)
  assign(pop, b, envir = .base)
  b
}

# ---------------------------------------------------------------- página
corpo_html <- paste(readLines(file.path(raiz, "assets", "figura1_corpo.html"), encoding = "UTF-8", warn = FALSE), collapse = "\n")

# Controles que só existem no app: população, causa do óbito e o que retirar do ajuste (o JavaScript da figura os reconhece pelo id).
controles_shiny <- function(pops, pop) {
  opc_pop <- if (length(pops) < 2) "" else sprintf("\n    <label>População<select id=\"s-pop\">%s</select></label>",
    paste0(sprintf("<option value=\"%s\"%s>%s</option>", pops, ifelse(pops == pop, " selected", ""), ROTULO_POP[pops]), collapse = ""))
  causas <- sprintf("\n    <label>Causa do óbito<select id=\"s-causa\">%s</select></label>",
                    paste0(sprintf("<option value=\"%s\">%s</option>", names(CAUSAS), CAUSAS), collapse = ""))
  retirar <- paste0("\n    <fieldset class=\"ret\"><legend>Retirar do ajuste do modelo</legend>",
    "<label class=\"chk\"><input type=\"checkbox\" id=\"s-r-covid\"> <span id=\"s-r-covid-t\">Período COVID</span></label>",
    "<label class=\"chk\"><input type=\"checkbox\" id=\"s-r-nc\"> Meses com registro não consolidado</label>",
    "<label class=\"chk\"><input type=\"checkbox\" id=\"s-r-clima\"> Dias sem dados de clima (e os 10 seguintes)</label></fieldset>")
  paste0(opc_pop, causas, retirar)
}

modelo_pagina <- paste0(
  "<!DOCTYPE html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n",
  "<title>Mortalidade e calor no município do Rio de Janeiro</title>\n{{ headContent() }}\n<link rel=\"stylesheet\" href=\"painel/figura1.css\">\n</head>\n<body>\n",
  "{{ corpo }}\n<div id=\"tab-sobre\" class=\"sobre hide\">{{ metodos }}</div>\n</div>\n",
  "<script id=\"dados-b64\" type=\"text/plain\">{{ dados }}</script>\n<script src=\"painel/chart.umd.js\"></script>\n<script src=\"painel/figura1.js\"></script>\n</body>\n</html>")

pagina_sem_cache <- function() {
  st <- tryCatch(jsonlite::fromJSON(file.path(pasta, "ultima_tentativa.json")), error = function(e) NULL)
  msg <- if (!is.null(st) && st$status %in% c("offline", "falhou"))
    sprintf("A última tentativa de baixar os dados (%s) terminou com o status \"%s\": %s. Confira a conexão do servidor com o GitHub e rode shiny/atualizar_cache.R.", st$quando, st$status, st$detalhe)
  else "O servidor está baixando e preparando os dados das Releases do GitHub. Isso leva cerca de 1 a 2 minutos na primeira vez. Esta página recarrega sozinha."
  httpResponse(200, "text/html; charset=UTF-8", paste0("<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"20\"><title>Preparando os dados</title>",
              "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:15vh auto;padding:0 16px;color:#222}</style></head><body>",
              "<h1 style=\"font-size:20px\">Preparando os dados do painel</h1><p>", msg, "</p></body></html>"))
}

# Primeira visita sem cache: dispara a atualização em segundo plano (uma só vez por tentativa recente).
disparar_atualizacao <- function() {
  recente <- file.exists(file.path(pasta, "bloqueio")) ||
    (file.exists(f <- file.path(pasta, "ultima_tentativa.json")) && difftime(Sys.time(), file.mtime(f), units = "mins") < 10)
  if (recente) return(invisible(FALSE))
  dir.create(pasta, showWarnings = FALSE, recursive = TRUE)
  rscript <- file.path(R.home("bin"), "Rscript")
  system2(rscript, c(shQuote(file.path(raiz, "shiny", "atualizar_cache.R")), "--cache", shQuote(pasta)),
          stdout = file.path(pasta, "app_atualizacao.log"), stderr = file.path(pasta, "app_atualizacao.log"), wait = FALSE)
  invisible(TRUE)
}

ui <- function(req) {
  pops <- pops_prontas()
  if (!length(pops)) { disparar_atualizacao(); return(pagina_sem_cache()) }
  pop <- pops[1]
  b <- base_info(pop)
  if (is.null(b)) { disparar_atualizacao(); return(pagina_sem_cache()) }
  htmlTemplate(text_ = modelo_pagina, document_ = TRUE,
               corpo = HTML(sub("<div class=\"ctl\">", paste0("<div class=\"ctl\">", controles_shiny(pops, pop)), corpo_html, fixed = TRUE)),
               metodos = uiOutput("metodos"), dados = dados_b64(b$json_base))
}

# ---------------------------------------------------------------- servidor
erro_para_cliente <- function(e) {
  m <- conditionMessage(e)
  codigo <- if (grepl("^dados_mudaram:", m)) "dados_mudaram" else if (grepl("^recorte_invalido:", m)) "recorte_invalido" else "erro"
  if (codigo == "erro") message("[painel] erro no ajuste: ", m)                    # o detalhe fica no log do servidor
  list(codigo = codigo, mensagem = if (codigo == "erro") "erro interno no ajuste (veja o log do servidor)" else sub("^[a-z_]+: ", "", m))
}

texto1 <- function(v) is.character(v) && length(v) == 1 && !is.na(v)

server <- function(input, output, session) {
  pop <- reactiveVal(pops_prontas()[1])

  observeEvent(input$pop, {
    p <- input$pop
    if (!texto1(p) || !p %in% pops_prontas()) return()
    b <- base_info(p)
    if (is.null(b)) return()
    pop(p)
    session$sendCustomMessage("base", list(json = b$json_troca))
  }, ignoreInit = TRUE)

  output$metodos <- renderUI({
    b <- base_info(pop())
    req(b)
    HTML(commonmark::markdown_html(b$metodos, extensions = TRUE))
  })

  observeEvent(input$pedido, {
    q <- input$pedido
    campos <- c("key", "ex", "pop", "chave", "causa", "opc")
    if (!is.list(q) || !all(campos %in% names(q)) || !all(vapply(q[campos], texto1, TRUE))) return()
    eco <- list(pop = q$pop, key = q$key, ex = q$ex, chave = q$chave, causa = q$causa, opc = q$opc)
    erro <- function(codigo, mensagem) session$sendCustomMessage("erro_segmento", c(eco, list(codigo = codigo, mensagem = mensagem)))
    b <- if (q$pop %in% names(ROTULO_POP)) base_info(q$pop) else NULL
    if (is.null(b)) return(erro("recorte_invalido", "população fora da lista"))
    if (!identical(b$chave, q$chave)) return(erro("dados_mudaram", "os dados foram atualizados no servidor"))
    if (!q$causa %in% names(CAUSAS) || !codigo_valido(q$opc) || !q$ex %in% names(EXPOSICOES)) return(erro("recorte_invalido", "causa, retiradas ou medida de calor fora da lista"))
    if (!q$key %in% b$elegiveis[[q$causa]][[q$opc]]) return(erro("recorte_invalido", "recorte fora da lista ou com poucos óbitos no ajuste"))

    pedir_ajuste(raiz, pasta, q$pop, q$chave, q$key, q$ex, q$causa, q$opc) |>
      promises::then(
        onFulfilled = function(r) if (!session$isClosed()) session$sendCustomMessage("segmento", c(eco, list(json = json_utf8(r$payload)))),
        onRejected = function(e) if (!session$isClosed()) { x <- erro_para_cliente(e); erro(x$codigo, x$mensagem) })
    invisible(NULL)                                                                  # a sessão não espera o ajuste: outros pedidos seguem
  })
}

shinyApp(ui, server)
