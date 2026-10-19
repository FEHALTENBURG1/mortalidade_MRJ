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
checar("base: marca o modo sob demanda e traz a lista de recortes de cada causa e de cada combinação de retiradas",
       isTRUE(b$meta$sob_demanda) && setequal(names(b$meta$elegiveis), names(CAUSAS)) && all(vapply(b$meta$elegiveis, function(x) setequal(names(x), CODIGOS_OPC), TRUE)))
checar("base: causas naturais sem retiradas dão exatamente os recortes do JSON completo", setequal(unlist(b$meta$elegiveis$naturais[["000"]]), unlist(ref$k)))
checar("base: tirar mais dias do ajuste nunca acrescenta recortes", all(vapply(names(CAUSAS), function(ca)
  all(vapply(CODIGOS_OPC, function(cod) all(unlist(b$meta$elegiveis[[ca]][[cod]]) %in% unlist(b$meta$elegiveis[[ca]][["000"]])), TRUE)), TRUE)))
checar("base: todas as causas têm pelo menos os recortes das causas naturais", all(unlist(b$meta$elegiveis$naturais[["000"]]) %in% unlist(b$meta$elegiveis$todas[["000"]])))
checar("base: traz a distribuição de raça/cor de cada causa", setequal(names(b$rcs), names(CAUSAS)) && sum(unlist(b$rcs$todas)) > sum(unlist(b$rcs$naturais)))
checar("base: mesmos dias, clima e calendário do JSON completo", identical(unlist(json_de(b)$dias), unlist(ref$dias)) && identical(json_de(b)$sem, ref$sem) && identical(json_de(b)$cl, ref$cl))
checar("base: traz a versão dos dados", identical(b$meta$dados$chave, chave))
checar("base: é pequena (sem séries de recortes)", nchar(json_utf8(b)) < 0.1 * file.size(base_in), nchar(json_utf8(b)))

# causa do óbito e retiradas do ajuste
K <- "Todos os locais|Todas as idades"; cx <- P$cx
nas <- function(x) is.na(num(x))
r_nat <- pegar(K, "horas")$payload
o_nat <- num(json_de(r_nat)$o)
total <- function(causa) sum(num(json_de(executar_ajuste(pasta, "res", chave, K, "horas", causa, "000")$payload)$o), na.rm = TRUE)
t_nat <- sum(o_nat, na.rm = TRUE); t_sc <- total("todas_sem_covid"); t_todas <- total("todas"); t_ext <- total("externas")
checar("causas: todas sem COVID = naturais + externas", t_sc == t_nat + t_ext, c(t_sc, t_nat, t_ext))
checar("causas: todas com COVID soma os óbitos de COVID", t_todas - t_sc == sum(cx$d_extra$covid) && t_todas > t_sc, c(t_todas, t_sc, sum(cx$d_extra$covid)))
checar("causas: naturais batem com a série do JSON completo", exato(o_nat, ref$o[[match(K, unlist(ref$k))]]))
checar("causas: o contexto traz as causas não naturais com a marca de COVID", is.data.frame(cx$d_extra) && all(c("covid", COLUNAS_SERIE) %in% names(cx$d_extra)) && is.null(cx$d_todas_causas) && is.null(cx$cl_completo))
r_cov <- executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "100")
r_nc  <- executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "010")
r_cli <- executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "001")
r_ext <- executar_ajuste(pasta, "res", chave, K, "horas", "externas", "000")
e_nat <- json_de(r_nat)$e; sin <- json_de(r_nat)$S$e
checar("retiradas: sem retirada, só os dias sem registro no SIM ficam sem esperado", identical(nas(e_nat), as.logical(cx$sem_registro)))
j_cov <- json_de(r_cov$payload)
checar("retirar COVID: os dias de COVID ficam sem esperado, os demais continuam", all(nas(j_cov$e)[cx$covid]) && identical(nas(j_cov$e), as.logical(cx$sem_registro | cx$covid)))
checar("retirar COVID: as semanas de COVID ficam sem esperado semanal", all(nas(j_cov$S$e)[P$cov_w]) && !all(nas(j_cov$S$e)))
checar("retirar COVID: o observado não muda e o resultado muda", exato(j_cov$o, o_nat) && !igual(j_cov$rr, json_de(r_nat)$rr, 0.0001))
j_nc <- json_de(r_nc$payload)
checar("retirar meses não consolidados: esses dias ficam sem esperado", all(nas(j_nc$e)[cx$nao_consolidado]) && identical(nas(j_nc$e), as.logical(cx$sem_registro | cx$nao_consolidado)))
j_cli <- json_de(r_cli$payload)
fora_cli <- fora_ajuste(cx, list(covid = FALSE, nc = FALSE, clima = TRUE))
checar("retirar dias sem clima: eles e os dez seguintes ficam sem esperado", identical(nas(j_cli$e), as.logical(fora_cli)) && sum(fora_cli) > sum(cx$sem_registro))
j_ext <- json_de(r_ext$payload)
checar("causas externas: série própria, mais baixa que a de naturais", sum(num(j_ext$o), na.rm = TRUE) == t_ext && t_ext < t_nat)
fa <- c(arquivo_ajuste(pasta, chave, "res", "horas", K), arquivo_ajuste(pasta, chave, "res", "horas", K, "naturais", "100"), arquivo_ajuste(pasta, chave, "res", "horas", K, "externas", "000"),
        arquivo_ajuste(pasta, chave, "res", "horas", K, "externas", "100"))
checar("causa e retiradas diferentes usam arquivos diferentes", length(unique(fa)) == 4 && all(file.exists(fa[1:3])))
f_ok <- arquivo_ajuste(pasta, chave, "res", "horas", K, "todas", "000"); f_fake <- arquivo_ajuste(pasta, chave, "res", "horas", K, "naturais", "111")
file.copy(f_ok, f_fake, overwrite = TRUE)         # simula uma colisão de nomes: o arquivo guarda a causa e as retiradas e é recusado se não forem as pedidas
checar("o ajuste guardado de uma causa não é lido como de outra", !is.null(ler_ajuste(pasta, chave, "res", "horas", K, "todas", "000")) && is.null(ler_ajuste(pasta, chave, "res", "horas", K, "naturais", "111")))
unlink(f_fake)
r_cov2 <- executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "100")
checar("o mesmo pedido com retirada sai do disco", r_cov2$do_cache && identical(r_cov2$payload, r_cov$payload))
cvj <- json_de(r_nat)$cv; rrj <- json_de(r_nat)$rr
checar("curvas: o payload do app traz a grade de exposição, o RR acumulado e dois níveis de referência", !is.null(cvj) && length(cvj$x) == 41 && cvj$x[[1]] == 0 && cvj$rr[[1]] == 1 && length(cvj$lag) == 2)
checar("curvas: o RR acumulado na última defasagem é o RR dos quadros", abs(cvj$lag[[1]]$ac[[11]] - rrj[[1]]) < 5e-4 && abs(cvj$lag[[2]]$ac[[11]] - rrj[[4]]) < 5e-4, c(cvj$lag[[1]]$ac[[11]], rrj[[1]]))
checar("curvas: o intervalo envolve a curva e há 11 defasagens", all(num(cvj$lo) <= num(cvj$rr) + 1e-9) && all(num(cvj$rr) <= num(cvj$hi) + 1e-9) && length(cvj$lag[[1]]$rr) == 11 && length(cvj$lag[[2]]$achi) == 11)
checar("curvas: o payload sem o pedido de curvas (Quarto) não as traz", is.null(json_de(payload_segmento(ajustar_segmento(y_causa(P, "naturais")[[K]], P$b, cbi_de(P, "horas"), fora_ajuste(cx, opc_de_codigo("000")), P$kt), y_causa(P, "naturais")[[K]], P$sem, P$cov_w))$cv))
f_v <- arquivo_ajuste(pasta, chave, "res", "horas", K); x_v <- readRDS(f_v); x_v$versao <- NULL; saveRDS(x_v, f_v)
checar("ajuste gravado por versão antiga do payload é refeito", is.null(ler_ajuste(pasta, chave, "res", "horas", K)) && !executar_ajuste(pasta, "res", chave, K, "horas")$do_cache)
checar("causa fora da lista: erro recorte_invalido", identical(cod(executar_ajuste(pasta, "res", chave, K, "horas", "inexistente", "000")), "recorte_invalido"))
checar("retirada fora da lista: erro recorte_invalido", all(vapply(c("2", "1000", "abc", NA_character_), function(x) identical(cod(executar_ajuste(pasta, "res", chave, K, "horas", "naturais", x)), "recorte_invalido"), TRUE)))
checar("poucos óbitos depois da retirada: erro recorte_invalido", {
  el <- unlist(b$meta$elegiveis$naturais[["000"]]); sem111 <- setdiff(el, unlist(b$meta$elegiveis$naturais[["111"]]))
  length(sem111) == 0 || identical(cod(executar_ajuste(pasta, "res", chave, sem111[1], "horas", "naturais", "111")), "recorte_invalido") })

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
res3 <- NULL; err3 <- NULL
promises::then(pedir_ajuste(raiz, pasta, "res", chave, "Via pública|40-49", "horas", "externas", "110"), function(v) res3 <<- v, function(e) err3 <<- e)
t0 <- Sys.time(); while (is.null(res3) && is.null(err3) && difftime(Sys.time(), t0, units = "secs") < 180) later::run_now(0.2)
checar("pedido assíncrono com causa e retiradas termina e grava o ajuste", !is.null(res3) && is.null(err3) && !res3$do_cache && file.exists(arquivo_ajuste(pasta, chave, "res", "horas", "Via pública|40-49", "externas", "110")), if (!is.null(err3)) conditionMessage(err3) else "")
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
