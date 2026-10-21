#!/usr/bin/env Rscript
# Atualiza o cache de dados do painel Shiny a partir das Releases do GitHub (SIM e HAAT).
#
# Uso (de qualquer pasta):
#   Rscript shiny/atualizar_cache.R [--cache pasta] [--pop res,todos] [--forcar] [--aquecer] [--aquecer-cid]
#
# --cache   pasta do cache (padrão: variável PAINEL_CACHE ou <projeto>/shiny/cache). Precisa ser gravável por quem roda este script e pelo usuário do Shiny Server.
# --pop     populações a preparar: res (residentes que morreram no Rio) e/ou todos (todos os óbitos ocorridos no Rio)
# --forcar  refaz o cache mesmo que a versão das Releases não tenha mudado
# --aquecer depois de atualizar, ajusta o recorte inicial do app (todos os locais, todas as idades, causas naturais, sem retiradas) para as duas
#           medidas de calor e as 13 colunas do mapa de horas por limiar, de modo que o primeiro usuário já encontre tudo pronto. Leva alguns minutos
#           por população na primeira vez depois de uma atualização dos dados e segundos nas seguintes (os ajustes ficam em disco). Falha aqui não muda o código de saída.
# --aquecer-cid  o mesmo para a aba Causas específicas (CID-10): ajusta, no recorte inicial, cada causa básica com pelo menos 1.500 óbitos (cerca de 100 causas)
#           para as duas medidas de calor. Leva de 15 a 30 minutos por população na primeira vez, por isso é uma opção à parte (pode rodar em segundo plano com nohup).
#
# Para rodar todo dia às 06:00, com o usuário que executa os apps (crontab -e de `sudo -u shiny crontab -e`):
#   0 6 * * *  /usr/bin/Rscript /opt/mortalidade_MRJ/painel_quarto/shiny/atualizar_cache.R >> /opt/mortalidade_MRJ/painel_quarto/shiny/cache/cron.log 2>&1
# (ajuste o caminho do projeto e confirme o do Rscript com `which Rscript`)
#
# Código de saída: 0 se o cache está em dia, foi atualizado, há outra atualização em andamento, ou o GitHub está fora mas já existe cache; 1 nos demais casos.

invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
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
for (f in c("funcoes.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))

r <- atualizar_cache(pasta, pops, cnes = file.path(raiz, "dados_auxiliares", "cnes_estab.csv"),
                     arquivo_regras = file.path(raiz, "R", "funcoes.R"), forcar = "--forcar" %in% args)
ok <- r$status %in% c("atual", "atualizado", "ocupado") || (r$status == "offline" && r$tem_cache)

if (any(c("--aquecer", "--aquecer-cid") %in% args) && ok) {
  for (f in c("modelo_joao.R", "exportar.R")) fonte_utf8(file.path(raiz, "R", f))
  recorte <- "Todos os locais|Todas as idades"
  for (pop in pops) tryCatch({
    chave <- meta_cache(pasta, pop)$chave
    if (is.null(obter_P(pasta, pop, chave))) stop("sem contexto no cache")
    pedidos <- if ("--aquecer" %in% args) c("horas", "haat", paste0("mapa", LIMIARES)) else character(0)
    if ("--aquecer-cid" %in% args) {
      causas <- jsonlite::fromJSON(executar_ajuste(pasta, pop, chave, recorte, "cidlista", "naturais", COD_PADRAO)$payload)$cid
      pedidos <- c(pedidos, as.vector(rbind(paste0("cid_", causas, "_horas"), paste0("cid_", causas, "_haat"))))
    }
    for (expo in pedidos) {
      x <- executar_ajuste(pasta, pop, chave, recorte, expo, "naturais", COD_PADRAO)
      cat(format(Sys.time(), "%Y-%m-%d %H:%M:%S"), pop, expo, if (x$do_cache) "no disco" else sprintf("ajustado em %.0f s", x$segundos), "\n")
    }
  }, error = function(e) cat(format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "aquecimento de", pop, "interrompido:", conditionMessage(e), "\n"))
}
quit(save = "no", status = if (ok) 0L else 1L)
