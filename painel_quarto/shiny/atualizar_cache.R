#!/usr/bin/env Rscript
# Atualiza o cache de dados do painel Shiny a partir das Releases do GitHub (SIM e HAAT).
#
# Uso (de qualquer pasta):
#   Rscript shiny/atualizar_cache.R [--cache pasta] [--pop res,todos] [--forcar]
#
# --cache   pasta do cache (padrão: variável PAINEL_CACHE ou <projeto>/shiny/cache). Precisa ser gravável por quem roda este script e pelo usuário do Shiny Server.
# --pop     populações a preparar: res (residentes que morreram no Rio) e/ou todos (todos os óbitos ocorridos no Rio)
# --forcar  refaz o cache mesmo que a versão das Releases não tenha mudado
#
# Para rodar todo dia às 06:00, com o usuário que executa os apps (crontab -e de `sudo -u shiny crontab -e`):
#   0 6 * * *  Rscript /srv/shiny-server/painel_quarto/shiny/atualizar_cache.R >> /srv/shiny-server/painel_quarto/shiny/cache/cron.log 2>&1
#
# Código de saída: 0 se o cache está em dia, foi atualizado, há outra atualização em andamento, ou o GitHub está fora mas já existe cache; 1 nos demais casos.

try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE)
args <- commandArgs(trailingOnly = TRUE)
opcao <- function(nome, padrao = NULL) { i <- match(paste0("--", nome), args); if (is.na(i)) padrao else args[i + 1] }
raiz <- local({
  a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  if (length(a)) dirname(dirname(normalizePath(a[1]))) else normalizePath("..")
})
pasta <- opcao("cache", Sys.getenv("PAINEL_CACHE", file.path(raiz, "shiny", "cache")))
pops  <- strsplit(opcao("pop", "res,todos"), ",")[[1]]
stopifnot(all(pops %in% c("res", "todos")))

source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "fontes_remotas.R")) fonte_utf8(file.path(raiz, "R", f))

r <- atualizar_cache(pasta, pops, cnes = file.path(raiz, "dados_auxiliares", "cnes_estab.csv"),
                     arquivo_regras = file.path(raiz, "R", "funcoes.R"), forcar = "--forcar" %in% args)
ok <- r$status %in% c("atual", "atualizado", "ocupado") || (r$status == "offline" && r$tem_cache)
quit(save = "no", status = if (ok) 0L else 1L)
