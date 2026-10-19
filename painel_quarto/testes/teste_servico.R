#!/usr/bin/env Rscript
# Testa o serviço de ajuste sob demanda (R/servico.R): o payload de cada recorte tem de ser igual ao que calcular_figura1.R grava no JSON completo,
# o cache em disco tem de funcionar e os erros têm de sair com o código certo.
#
# Uso, a partir da pasta do projeto:
#   PAINEL_CACHE=/caminho/do/cache PAINEL_TESTE_BASE=/caminho/figura1_res.json Rscript testes/teste_servico.R
# PAINEL_CACHE: cache de dados já montado (shiny/atualizar_cache.R ou testes/montar_cache_local.R), com a população res.
# PAINEL_TESTE_BASE: figura1_res.json gerado por calcular_figura1.R com os MESMOS dados (a referência). Sem eles, o teste é pulado.

invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(dirname(normalizePath(a[1]))) else getwd() })
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))

falhas <- character(0)
checar <- function(nome, cond, detalhe = "") {
  ok <- isTRUE(cond); cat(sprintf("%s %s%s\n", if (ok) "ok    " else "FALHOU", nome, if (!ok && nzchar(detalhe)) paste0(" | ", detalhe) else ""))
  if (!ok) falhas <<- c(falhas, nome)
}

cache_in <- Sys.getenv("PAINEL_CACHE"); base_in <- Sys.getenv("PAINEL_TESTE_BASE")
if (!nzchar(cache_in) || !nzchar(base_in) || !file.exists(base_in) || is.null(meta_cache(cache_in, "res"))) {
  cat("PULADO: defina PAINEL_CACHE (cache com a população res) e PAINEL_TESTE_BASE (figura1_res.json de referência).\n"); quit(save = "no", status = 0L)
}

# cache de trabalho próprio (links para o contexto), para não misturar os ajustes do teste com os de um app em uso
pasta <- tempfile("cache_servico_"); dir.create(pasta)
for (f in c(Sys.glob(file.path(cache_in, "contexto_res_*.rds")), file.path(cache_in, "meta_res.json"))) file.symlink(normalizePath(f), file.path(pasta, basename(f)))
chave <- meta_cache(pasta, "res")$chave

ref <- jsonlite::fromJSON(base_in, simplifyVector = FALSE)
json_de <- function(x) jsonlite::fromJSON(json_utf8(x), simplifyVector = FALSE)     # o que o navegador recebe
num <- function(x) as.numeric(unlist(lapply(x, function(v) if (is.null(v)) NA_real_ else v)))
# mesma série, ainda que um valor caia do outro lado de um arredondamento (diferença de uma unidade da última casa)
igual <- function(a, b, passo) { a <- num(a); b <- num(b); length(a) == length(b) && all(is.na(a) == is.na(b)) && all(abs(a - b) <= passo * 1.001 + 1e-9, na.rm = TRUE) }
exato <- function(a, b) identical(num(a), num(b))

comparar <- function(payload, key, expo) {
  p <- json_de(payload); k <- match(key, unlist(ref$k)); m <- ref$m[[expo]]; S <- ref$S[[expo]][[key]]
  c(f = identical(p$f, m$f[[k]]), d = igual(p$d, m$d[[k]], 0.001), rr = igual(p$rr, m$rr[[k]], 0.0001), e = igual(p$e, m$e[[k]], 1),
    o = exato(p$o, ref$o[[k]]), So = exato(p$So, ref$So[[key]]),
    Se = igual(p$S$e, S$e, 0.1), Sl = igual(p$S$l, S$l, 0.1), Su = igual(p$S$u, S$u, 0.1), Sphi = igual(p$S$phi, S$phi, 0.01))
}

recortes <- c("Todos os locais|Todas as idades", "Domicílio|60-69", "Hospital|Todas as idades|Parda")
pegar <- function(key, expo) executar_ajuste(pasta, "res", chave, key, expo)
tempos <- numeric(0)
for (key in recortes) for (expo in c("horas", "haat")) {
  r <- pegar(key, expo); tempos <- c(tempos, r$segundos)
  cmp <- comparar(r$payload, key, expo)
  checar(sprintf("payload = JSON completo: %s, %s (%.1f s)", key, expo, r$segundos), !r$do_cache && all(cmp), paste(names(cmp)[!cmp], collapse = ","))
}
cat(sprintf("       tempo médio de ajuste por recorte: %.1f s (n = %d)\n", mean(tempos), length(tempos)))

# cache em disco
r2 <- pegar(recortes[2], "horas")
checar("2ª chamada do mesmo recorte vem do disco, sem refazer o modelo", r2$do_cache && r2$segundos == 0)
checar("o payload do disco é igual ao calculado", all(comparar(r2$payload, recortes[2], "horas")))
f <- arquivo_ajuste(pasta, chave, "res", "horas", recortes[2])
writeLines("lixo", f)
r3 <- pegar(recortes[2], "horas")
checar("arquivo de ajuste corrompido é refeito", !r3$do_cache && all(comparar(r3$payload, recortes[2], "horas")))
checar("recortes diferentes usam arquivos diferentes", length(unique(vapply(recortes, function(k) arquivo_ajuste(pasta, chave, "res", "horas", k), ""))) == length(recortes))

# erros com código
cod <- function(expr) tryCatch({ expr; "sem erro" }, error = function(e) sub(":.*", "", conditionMessage(e)))
checar("versão de dados antiga: erro dados_mudaram", identical(cod(executar_ajuste(pasta, "res", "chave_antiga", recortes[1], "horas")), "dados_mudaram"))
checar("recorte fora da lista: erro recorte_invalido", identical(cod(pegar("Local inexistente|Todas as idades", "horas")), "recorte_invalido"))
checar("recorte com poucos óbitos: erro recorte_invalido", identical(cod(pegar("Ignorado|30-39", "horas")), "recorte_invalido"))
checar("medida de calor fora da lista: erro recorte_invalido", identical(cod(pegar(recortes[1], "frio")), "recorte_invalido"))
checar("população sem cache: erro dados_mudaram", identical(cod(executar_ajuste(pasta, "todos", chave, recortes[1], "horas")), "dados_mudaram"))

# dados-base
P <- obter_P(pasta, "res")
b <- base_sob_demanda(P)
checar("base: marca o modo sob demanda e traz a lista de recortes", isTRUE(b$meta$sob_demanda) && length(b$meta$elegiveis) == length(ref$k) && setequal(b$meta$elegiveis, unlist(ref$k)))
checar("base: mesmos dias, clima e calendário do JSON completo", identical(unlist(json_de(b)$dias), unlist(ref$dias)) && identical(json_de(b)$sem, ref$sem) && identical(json_de(b)$cl, ref$cl))
checar("base: traz a versão dos dados", identical(b$meta$dados$chave, chave))
checar("base: é pequena (sem séries de recortes)", nchar(json_utf8(b)) < 0.1 * file.size(base_in), nchar(json_utf8(b)))

# pedidos assíncronos pelo future: pedidos iguais compartilham a promessa e o resultado é o mesmo
suppressWarnings(future::plan("multisession", workers = 1))
p1 <- pedir_ajuste(raiz, pasta, "res", chave, "Via pública|40-49", "horas")                 # a primeira chamada sobe o trabalhador e cria o pedido
t_2 <- system.time(p2 <- pedir_ajuste(raiz, pasta, "res", chave, "Via pública|40-49", "horas"))[["elapsed"]]
checar("pedido igual em andamento não abre outro trabalho", t_2 < 0.5 && length(ls(.pendentes, all.names = TRUE)) == 1, sprintf("%.2f s, %d pendentes", t_2, length(ls(.pendentes, all.names = TRUE))))
res <- NULL; err <- NULL; res_b <- NULL
promises::then(p2, function(v) res_b <<- v)
promises::then(p1, function(v) res <<- v, function(e) err <<- e)
t0 <- Sys.time(); while (is.null(res) && is.null(err) && difftime(Sys.time(), t0, units = "secs") < 180) later::run_now(0.2)
checar("pedido assíncrono termina e traz o payload", !is.null(res) && is.null(err) && all(comparar(res$payload, "Via pública|40-49", "horas")), if (!is.null(err)) conditionMessage(err) else "")
res2 <- NULL; promises::then(pedir_ajuste(raiz, pasta, "res", chave, "Via pública|40-49", "horas"), function(v) res2 <<- v)
t0 <- Sys.time(); while (is.null(res2) && difftime(Sys.time(), t0, units = "secs") < 20) later::run_now(0.1)
checar("os dois pedidos iguais recebem o mesmo payload", !is.null(res_b) && identical(res_b$payload, res$payload))
checar("o mesmo pedido de novo sai do disco na hora", !is.null(res2) && res2$do_cache)
err2 <- NULL; promises::then(pedir_ajuste(raiz, pasta, "res", "chave_antiga", recortes[1], "haat"), function(v) NULL, function(e) err2 <<- e)
t0 <- Sys.time(); while (is.null(err2) && difftime(Sys.time(), t0, units = "secs") < 60) later::run_now(0.2)
checar("erro no trabalhador chega à promessa com o código", !is.null(err2) && grepl("^dados_mudaram:", conditionMessage(err2)))
suppressWarnings(future::plan("sequential"))

# limpeza de versões antigas
dir.create(file.path(pasta, "ajustes", "velha1"), recursive = TRUE); dir.create(file.path(pasta, "ajustes", "velha2"), recursive = TRUE)
n <- limpar_ajustes_antigos(pasta, chave)
checar("limpar_ajustes_antigos apaga só as pastas de outras versões", n == 2 && dir.exists(file.path(pasta, "ajustes", chave)) && !dir.exists(file.path(pasta, "ajustes", "velha1")))

unlink(pasta, recursive = TRUE)
cat("\nFALHAS:", if (!length(falhas)) "nenhuma" else paste(falhas, collapse = "; "), "\n")
quit(save = "no", status = if (length(falhas)) 1L else 0L)
