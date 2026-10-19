#!/usr/bin/env Rscript
# Monta um cache de dados a partir de arquivos locais (sem rede), no mesmo formato que shiny/atualizar_cache.R. Serve para testar o app Shiny e o
# serviço de ajustes sem depender do GitHub.
#   Rscript testes/montar_cache_local.R --silver pasta/silver --haat haat_diario_municipal.csv --cache pasta_do_cache [--pop res,todos] [--chave abc123]
invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
args <- commandArgs(trailingOnly = TRUE)
opcao <- function(nome, padrao = NULL) { i <- match(paste0("--", nome), args); if (is.na(i)) padrao else args[i + 1] }
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(dirname(normalizePath(a[1]))) else getwd() })
silver <- opcao("silver"); haat <- opcao("haat"); pasta <- opcao("cache"); chave <- opcao("chave", "local0000001")
pops <- strsplit(opcao("pop", "res"), ",")[[1]]
stopifnot(!is.null(silver), !is.null(haat), !is.null(pasta))
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "fontes_remotas.R")) fonte_utf8(file.path(raiz, "R", f))
dir.create(pasta, showWarnings = FALSE, recursive = TRUE)
for (pop in pops) {
  cx <- contexto(silver, haat, file.path(raiz, "dados_auxiliares", "cnes_estab.csv"), pop)
  cx <- enxugar_contexto(cx)
  meta <- list(chave = chave, pop = pop, repo_sim = "local/teste", sim_atualizado = "2026-10-13T20:50:39Z", clima_atualizado = "2026-10-19T12:18:53Z",
               gerado_em = format(Sys.time(), "%Y-%m-%d %H:%M"), inicio = as.character(cx$inicio), fim = as.character(cx$fim), n_obitos = nrow(cx$d), n_dias = length(cx$dias))
  destino <- file.path(pasta, sprintf("contexto_%s_%s.rds", pop, chave))
  saveRDS(list(cx = cx, meta = meta), destino)
  jsonlite::write_json(meta, caminho_meta(pasta, pop), auto_unbox = TRUE)
  cat("cache", pop, "pronto:", destino, "\n")
}
