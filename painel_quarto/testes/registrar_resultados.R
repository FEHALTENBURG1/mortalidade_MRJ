#!/usr/bin/env Rscript
# Registra os resultados do modelo principal por versão dos dados, para a revisão metodológica do painel.
# Reajusta o recorte geral (Todos os locais, Todas as idades) nas duas populações (residentes e todos os óbitos ocorridos no Rio), nas causas naturais e
# externas, nas duas medidas de calor e em cinco combinações de retiradas do ajuste, e grava docs/revisao_resultados.md com:
#   1. a versão dos dados;
#   2. o resultado anterior (nada retirado do ajuste e dias sem clima contados como dias sem calor) e o novo (ajuste principal) lado a lado;
#   3. a matriz completa (população x causa x medida x retiradas).
#
# Uso (a partir da pasta painel_quarto):
#   PAINEL_CACHE=pasta_do_cache Rscript testes/registrar_resultados.R [--cache pasta] [--saida docs/revisao_resultados.md] [--cidlista pasta [--so-cidlista]]
# O cache precisa ter as populações res e todos (shiny/atualizar_cache.R ou testes/montar_cache_local.R). Cada ajuste vai para o cache em disco, como no app.

invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
args <- commandArgs(trailingOnly = TRUE)
opcao <- function(nome, padrao = NULL) { i <- match(paste0("--", nome), args); if (is.na(i)) padrao else args[i + 1] }
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(dirname(normalizePath(a[1]))) else getwd() })
pasta <- opcao("cache", Sys.getenv("PAINEL_CACHE", unset = ""))
if (!nzchar(pasta)) stop("Informe o cache (--cache pasta ou PAINEL_CACHE).")
saida <- opcao("saida", file.path(raiz, "docs", "revisao_resultados.md"))
Sys.setenv(OMP_NUM_THREADS = "1")
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "metodos.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))

CHAVE <- "Todos os locais|Todas as idades"
POPS <- c(res = "residentes no Rio com óbito ocorrido no município", todos = "todos os óbitos ocorridos no município, residentes ou não")
POP_CURTO <- c(res = "residentes", todos = "todos os óbitos")
fam_txt <- function(f) if (f == "nb") "binomial negativa" else "quase-Poisson"
CAUSAS_R <- c(naturais = "causas naturais", externas = "causas externas")
# código das retiradas: covid, meses não consolidados, dias sem clima (1 = retirado do ajuste)
CODS <- c("000" = "nada retirado; dias sem clima contados como dias sem calor (especificação anterior)",
          "010" = "meses não consolidados retirados",
          "001" = "dias sem clima (e os 10 seguintes) retirados",
          "011" = "meses não consolidados e dias sem clima retirados (ajuste principal)",
          "111" = "ajuste principal e período da COVID-19 retirado")
pt <- function(x, d = 2) format(round(x, d), nsmall = d, decimal.mark = ",", big.mark = ".", trim = TRUE)
rrtxt <- function(v) sprintf("%s (%s a %s)", pt(v[1]), pt(v[2]), pt(v[3]))
agora <- function() format(Sys.time(), "%H:%M:%S")

# Lista de causas da aba Causas específicas, para testes/conferir_independente.py (--cidlista pasta): um JSON por causa do óbito, no ajuste principal.
pasta_cid <- opcao("cidlista")
if (!is.null(pasta_cid)) {
  dir.create(pasta_cid, showWarnings = FALSE, recursive = TRUE)
  P <- obter_P(pasta, "res")
  for (causa in names(CAUSAS)) {
    x <- ajustar_recorte(P, CHAVE, "cidlista", causa, COD_PADRAO)
    writeLines(as.character(jsonlite::toJSON(x, auto_unbox = TRUE)), file.path(pasta_cid, sprintf("cid_%s.json", causa)), useBytes = TRUE)
  }
  cat("listas de causas gravadas em", pasta_cid, "\n")
  if ("--so-cidlista" %in% args) quit(save = "no")
}

lin <- list(); dados <- list()
for (pop in names(POPS)) {
  P <- obter_P(pasta, pop)
  if (is.null(P)) stop("Cache sem a população ", pop)
  dados[[pop]] <- P$meta
  for (causa in names(CAUSAS_R)) for (ex in names(EXPOSICOES)) for (cod in names(CODS)) {
    cat(agora(), pop, causa, ex, cod, "\n")
    x <- tryCatch(ajustar_recorte(P, CHAVE, ex, causa, cod), error = function(e) { message("falhou: ", conditionMessage(e)); NULL })
    if (is.null(x)) next
    rr <- as.numeric(x$rr)                                   # nível 1: estimativa, limite inferior, limite superior; nível 2: o mesmo
    lin[[length(lin) + 1]] <- list(pop = pop, causa = causa, ex = ex, cod = cod, rr1 = rr[1:3], rr2 = rr[4:6], fam = x$f, disp = x$d, nd = x$aj$nd, no = x$aj$no, ini = x$aj$ini, fim = x$aj$fim)
  }
}

niveis <- function(ex) { E <- EXPOSICOES[[ex]]; sprintf("%s %s", pt(E$ref, 0), E$unidade) }
M1 <- dados[[1]]
md <- c("# Revisão metodológica: resultados do modelo principal por versão dos dados", "",
        "Gerado por `testes/registrar_resultados.R`. Estudo ecológico de série temporal, com componente analítico. Os RR são da contagem diária de óbitos, acumulados em 0 a 10 dias, para a exposição mantida em todos os 11 dias em comparação com a ausência dessa exposição no mesmo intervalo, com IC 95% a partir da matriz de covariância dos coeficientes. Não são alertas operacionais.", "",
        "## Versão dos dados", "",
        "| População | Chave | SIM atualizado em | Clima atualizado em | Dados gerados em | Série | Óbitos por causas naturais | Dias |", "|:--|:--|:--|:--|:--|:--|--:|--:|")
for (pop in names(dados)) { m <- dados[[pop]]
  md <- c(md, sprintf("| %s | %s | %s | %s | %s | %s a %s | %s | %s |", POPS[[pop]], m$chave, m$sim_atualizado, m$clima_atualizado, m$gerado_em, m$inicio, m$fim, pt(m$n_obitos, 0), pt(m$n_dias, 0))) }
md <- c(md, "", sprintf("Versão do formato dos ajustes (`VERSAO_AJUSTE`): %s. Defasagem de 0 a %d dias (decisão de modelagem do painel; o protocolo municipal trabalha com 3 dias). Spline do tempo com k = %d.", VERSAO_AJUSTE, LAG, k_tempo(M1$n_dias)), "")

busca <- function(pop, causa, ex, cod) { for (l in lin) if (l$pop == pop && l$causa == causa && l$ex == ex && l$cod == cod) return(l); NULL }
md <- c(md, "## Resultado anterior e novo", "",
        "Anterior: nada retirado do ajuste e dias sem dado de clima contados como dias sem calor. Novo: ajuste principal, sem os meses de registro não consolidado e sem os dias sem clima (e os 10 seguintes). A variação é a diferença relativa do log-RR.", "",
        "| População | Causa | Medida de calor | Nível | RR anterior (IC 95%) | RR novo (IC 95%) | Variação do log-RR | Família anterior | Família nova |", "|:--|:--|:--|:--|:--|:--|--:|:--|:--|")
for (pop in names(POPS)) for (causa in names(CAUSAS_R)) for (ex in names(EXPOSICOES)) {
  a <- busca(pop, causa, ex, "000"); n <- busca(pop, causa, ex, "011"); if (is.null(a) || is.null(n)) next
  for (j in 1:2) {
    ra <- if (j == 1) a$rr1 else a$rr2; rn <- if (j == 1) n$rr1 else n$rr2
    md <- c(md, sprintf("| %s | %s | %s | %s | %s | %s | %s%% | %s | %s |", POP_CURTO[[pop]], CAUSAS_R[[causa]], EXPOSICOES[[ex]]$nome, niveis(ex)[j], rrtxt(ra), rrtxt(rn),
                        sub("-", "−", sprintf("%+d", round(100 * (log(rn[1]) - log(ra[1])) / log(ra[1])))), fam_txt(a$fam), fam_txt(n$fam)))
  }
}
md <- c(md, "", "## Matriz de retiradas, populações, causas e medidas", "",
        "Cada linha é um ajuste do recorte geral (todos os locais e todas as idades). Dias e óbitos são os do ajuste.", "",
        "| População | Causa | Medida de calor | Retiradas | Dias | Óbitos | Período do ajuste | Família | RR no 1º nível (IC 95%) | RR no 2º nível (IC 95%) |", "|:--|:--|:--|:--|--:|--:|:--|:--|:--|:--|")
for (l in lin) md <- c(md, sprintf("| %s | %s | %s | %s | %s | %s | %s a %s | %s (%s) | %s | %s |", POP_CURTO[[l$pop]], CAUSAS_R[[l$causa]], EXPOSICOES[[l$ex]]$nome, CODS[[l$cod]], pt(l$nd, 0), pt(l$no, 0),
                                       format(as.Date(l$ini), "%d/%m/%Y"), format(as.Date(l$fim), "%d/%m/%Y"), fam_txt(l$fam), if (l$fam == "nb") paste0("θ = ", pt(l$disp, 1)) else paste0("φ = ", pt(l$disp, 2)), rrtxt(l$rr1), rrtxt(l$rr2)))
md <- c(md, "", sprintf("Níveis de referência: %s.", paste(sprintf("%s: %s e %s", sapply(names(EXPOSICOES), function(e) EXPOSICOES[[e]]$nome), sapply(names(EXPOSICOES), function(e) niveis(e)[1]), sapply(names(EXPOSICOES), function(e) niveis(e)[2])), collapse = "; ")), "")
dir.create(dirname(saida), showWarnings = FALSE, recursive = TRUE)
writeLines(md, saida, useBytes = TRUE)
saveRDS(lin, sub("\\.md$", ".rds", saida))
cat(agora(), "gravado:", saida, "\n")
