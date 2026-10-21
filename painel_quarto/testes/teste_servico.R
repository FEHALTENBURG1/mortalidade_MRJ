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
checar("base: causas naturais no ajuste principal dão exatamente os recortes do JSON completo", setequal(unlist(b$meta$elegiveis$naturais[[COD_PADRAO]]), unlist(ref$k)))
checar("base: o ajuste principal tem os recortes da especificação anterior, menos os que perdem óbitos com as retiradas", all(unlist(b$meta$elegiveis$naturais[[COD_PADRAO]]) %in% unlist(b$meta$elegiveis$naturais[["000"]])) && length(unlist(b$meta$elegiveis$naturais[[COD_PADRAO]])) <= length(unlist(b$meta$elegiveis$naturais[["000"]])))
checar("base: traz a reconciliação das causas, que soma o total de óbitos elegíveis", { r <- b$meta$reconc; !is.null(r) && sum(r$grupos$n) == r$total && r$opcoes$naturais == nrow(P$cx$d) && r$opcoes$todas == r$total && r$opcoes$todas_sem_covid == r$total - sum(P$cx$d_extra$covid) })
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
r_000 <- executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "000")
e_nat <- json_de(r_nat)$e; sin <- json_de(r_nat)$S$e
checar("ajuste principal: ficam sem esperado os dias sem registro, os meses não consolidados e os dias sem clima (e os dez seguintes)", identical(nas(e_nat), as.logical(fora_ajuste(cx, opc_de_codigo(COD_PADRAO)))) && sum(nas(e_nat)) > sum(cx$sem_registro))
checar("ajuste principal: o payload traz o resumo do ajuste (dias, óbitos, período e dias fora por motivo)", { a <- json_de(r_nat)$aj; !is.null(a) && a$nd == sum(!fora_ajuste(cx, opc_de_codigo(COD_PADRAO))) && a$no == sum(num(json_de(r_nat)$o)[!fora_ajuste(cx, opc_de_codigo(COD_PADRAO))]) && length(a$xd) == length(MOTIVOS_FORA) && sum(unlist(a$xd)) + a$nd == length(cx$dias) && a$ini < a$fim })
checar("retiradas: sem retirada alguma (especificação anterior), só os dias sem registro no SIM ficam sem esperado", identical(nas(json_de(r_000$payload)$e), as.logical(cx$sem_registro)))
checar("retiradas: o ajuste principal muda o RR em relação à especificação anterior", !igual(json_de(r_nat)$rr, json_de(r_000$payload)$rr, 0.0001))
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

# mapa de horas por dia x limiar (Figura 4): uma coluna por pedido, "mapa<K>"
KM <- "Via pública|60-69"                                                     # recorte pequeno (cerca de 400 óbitos no ajuste principal), para o teste ser rápido
rm1 <- executar_ajuste(pasta, "res", chave, KM, "mapa36")
pm <- json_de(rm1$payload)
checar("mapa: a coluna traz o limiar, as 8 linhas de horas e os intervalos", identical(pm$tipo, "mapa") && pm$limiar == 36 && length(pm$h) == 8 && length(pm$rr) == 8 && length(pm$lo) == 8 && length(pm$hi) == 8 && length(pm$nd) == 8 && !rm1$do_cache)
est <- !is.na(num(pm$rr))
checar("mapa: o intervalo envolve a estimativa em toda célula estimada", any(est) && all(num(pm$lo)[est] < num(pm$rr)[est] & num(pm$rr)[est] < num(pm$hi)[est]))
checar("mapa: as células são aninhadas (mais horas, menos dias expostos)", all(diff(num(pm$nd)) <= 0))
checar("mapa: célula com menos de 15 dias expostos fica sem estimativa", all(is.na(num(pm$rr))[num(pm$nd) < MIN_DIAS_EXPOSTOS]) && all(!is.na(num(pm$rr))[num(pm$nd) >= MIN_DIAS_EXPOSTOS & num(pm$nd) <= pm$n]))
checar("mapa: o segundo pedido sai do disco", executar_ajuste(pasta, "res", chave, KM, "mapa36")$do_cache && identical(executar_ajuste(pasta, "res", chave, KM, "mapa36")$payload, rm1$payload))
# a célula (36 °C, 4 h) refeita à mão com o mesmo GAM deve dar o mesmo RR
h4 <- match(4, pm$h)
if (!is.na(num(pm$rr)[h4])) {
  yk <- y_causa(P, "naturais")[[KM]]; fora0 <- fora_ajuste(cx, opc_de_codigo(COD_PADRAO))
  nh <- cx$clima$num_hr_36; nh[is.na(nh)] <- 0; x4 <- as.numeric(nh >= 4)
  cb4 <- crossbasis(c(rep(0, LAG), x4), lag = LAG, argvar = list(fun = "lin"), arglag = list(fun = "ns", df = 3))
  cbi4 <- matrix(as.numeric(cb4[-seq_len(LAG), , drop = FALSE]), nrow = length(x4), dimnames = list(NULL, colnames(cb4)))
  dd4 <- P$b; dd4$y <- yk; dd4$y[fora0] <- NA
  ft4 <- suppressWarnings(gam(y ~ cbi4 + s(time_id, k = P$kt, bs = "tp") + s(dia_ano, k = 6, bs = "cc") + s(covid_id, k = 8, bs = "cc"), data = dd4, family = nb(), method = "REML"))
  ib4 <- grep("^cbi4", names(coef(ft4)))
  pr4 <- crosspred(cb4, coef = coef(ft4)[ib4], vcov = vcov(ft4)[ib4, ib4], model.link = "log", at = 1, cen = 0)
  checar("mapa: a célula (36 °C, 4 h) é o RR do GAM com a cross-basis binária ajustado à mão", abs(num(pm$rr)[h4] - pr4$allRRfit) < 1e-6 && abs(num(pm$lo)[h4] - pr4$allRRlow) < 1e-6 && abs(num(pm$hi)[h4] - pr4$allRRhigh) < 1e-6, c(num(pm$rr)[h4], pr4$allRRfit))
}
checar("mapa: outra causa e outras retiradas dão outra coluna", !identical(json_de(executar_ajuste(pasta, "res", chave, KM, "mapa36", "externas", "100")$payload)$rr, pm$rr))
checar("mapa: o arquivo de cache é próprio de cada limiar", !identical(arquivo_ajuste(pasta, chave, "res", "mapa36", KM), arquivo_ajuste(pasta, chave, "res", "mapa37", KM)))
checar("mapa: limiar fora de 32 a 44 ou id malformado: erro recorte_invalido", all(vapply(c("mapa31", "mapa45", "mapa3", "mapa036", "mapa36x", "mapa", "Mapa36"), function(x) identical(cod(executar_ajuste(pasta, "res", chave, KM, x)), "recorte_invalido"), TRUE)))
checar("mapa: recorte com poucos óbitos: erro recorte_invalido", identical(cod(executar_ajuste(pasta, "res", chave, "Ignorado|30-39", "mapa36")), "recorte_invalido"))
checar("mapa: versão de dados antiga: erro dados_mudaram", identical(cod(executar_ajuste(pasta, "res", chave2 <- "chave_antiga", KM, "mapa36")), "dados_mudaram"))
checar("mapa: expo_valida aceita as duas medidas e as colunas, e nada mais", all(vapply(c("horas", "haat", paste0("mapa", 32:44)), expo_valida, TRUE)) && !any(vapply(c("mapa31", "xyz", "", NA_character_), expo_valida, TRUE)))

# causas específicas (CID-10): lista de causas, RR por causa e série semanal
KC <- "Todos os locais|Todas as idades"
check_cid_soma <- function(causa, key) {                                  # as séries das causas somam a série do recorte
  r <- obitos_recorte_cid(P, causa, key)
  tot <- Reduce(`+`, lapply(unique(r$cid), function(c) y_cid(P, causa, key, c)))
  identical(as.integer(tot), as.integer(y_causa(P, causa)[[key]]))
}
checar("cid: as séries por causa somam a série do recorte (naturais, Todos os locais)", check_cid_soma("naturais", KC))
checar("cid: o mesmo para um recorte por local e faixa etária", check_cid_soma("naturais", "Domicílio|60-69"))
checar("cid: o mesmo para raça/cor e para todas as causas sem COVID", check_cid_soma("todas_sem_covid", "Hospital|Todas as idades|Parda"))
lc <- executar_ajuste(pasta, "res", chave, KC, "cidlista")
pl <- json_de(lc$payload)
checar("cid: a lista traz as causas com pelo menos CID_MIN óbitos, da maior para a menor", length(pl$cid) > 20 && length(pl$cid) == length(pl$n) && all(num(pl$n) >= CID_MIN) && !is.unsorted(rev(num(pl$n))), length(pl$cid))
checar("cid: a lista de causas externas só tem causas externas (letras V a Y)", { le <- json_de(executar_ajuste(pasta, "res", chave, KC, "cidlista", "externas")$payload)$cid; length(le) > 0 && all(substr(unlist(le), 1, 1) %in% c("V", "W", "X", "Y")) })
checar("cid: a lista com COVID retirada do ajuste tem menos óbitos por causa", { lr <- json_de(executar_ajuste(pasta, "res", chave, KC, "cidlista", "todas", "100")$payload); lo <- json_de(executar_ajuste(pasta, "res", chave, KC, "cidlista", "todas", "000")$payload); sum(num(lr$n)) < sum(num(lo$n)) })
cc <- executar_ajuste(pasta, "res", chave, KC, "cid_I21_horas")
pc <- json_de(cc$payload)
checar("cid: a causa traz RR, IC 95% e p nos dois níveis de referência", identical(pc$tipo, "cid") && identical(pc$cid, "I21") && length(pc$rr) == 2 && all(num(pc$lo) < num(pc$rr) & num(pc$rr) < num(pc$hi)) && all(num(pc$p) >= 0 & num(pc$p) <= 1) && !cc$do_cache)
checar("cid: o RR de todas as causas somadas é o do recorte (modelo da Figura 1) e o de uma causa parte do mesmo modelo", {
  y <- y_cid(P, "naturais", KC, "I21"); r <- ajustar_segmento(y, P$b, cbi_de(P, "horas"), fora_ajuste(P$cx, opc_de_codigo(COD_PADRAO)), P$kt)
  isTRUE(all.equal(num(pc$rr), round(as.numeric(r$rr["rr", ]), 4))) && isTRUE(all.equal(num(pc$p), unname(signif(2 * pnorm(-abs(log(r$rr["rr", ]) / r$se)), 4)))) })
checar("cid: com a medida de horas o valor de p é o mesmo nos dois níveis (resposta linear no log)", abs(num(pc$p)[1] - num(pc$p)[2]) < 1e-12)
checar("cid: o segundo pedido sai do disco", executar_ajuste(pasta, "res", chave, KC, "cid_I21_horas")$do_cache)
cs <- executar_ajuste(pasta, "res", chave, KC, "cidsem_I21_horas")
psj <- json_de(cs$payload)
checar("cid: a série semanal traz observado e esperado semanal com a faixa", identical(psj$tipo, "cidsem") && length(psj$So) == length(psj$S$e) && length(psj$S$l) == length(psj$S$u) && sum(num(psj$So)) > 0.5 * CID_MIN)
checar("cid: o RR da série semanal é o do pedido leve", isTRUE(all.equal(num(psj$rr)[c(1, 4)], num(pc$rr))))
checar("cid: causa fora do recorte ou sem óbitos suficientes: erro recorte_invalido", all(vapply(c("cid_Z99_horas", "cid_O80_horas", "cidsem_Z99_horas"), function(x) identical(cod(executar_ajuste(pasta, "res", chave, KC, x)), "recorte_invalido"), TRUE)))
checar("cid: ids malformados: erro recorte_invalido", all(vapply(c("cid_I21", "cid_I21_xyz", "cid_i21_horas", "cid_I2_horas", "cid_I211_horas", "cidlista2", "cidsem__horas", "CID_I21_horas"), function(x) identical(cod(executar_ajuste(pasta, "res", chave, KC, x)), "recorte_invalido"), TRUE)))
checar("cid: recorte inexistente: erro recorte_invalido", identical(cod(executar_ajuste(pasta, "res", chave, "Marte|Todas as idades", "cidlista")), "recorte_invalido"))
checar("cid: versão de dados antiga: erro dados_mudaram", identical(cod(executar_ajuste(pasta, "res", "chave_antiga", KC, "cidlista")), "dados_mudaram"))
checar("cid: expo_valida reconhece os pedidos de causa e só eles", all(vapply(c("cidlista", "cid_I21_haat", "cidsem_J18_horas"), expo_valida, TRUE)) && !any(vapply(c("cid_I21", "cidsem_I21_haat_x", "cid"), expo_valida, TRUE)))
checar("cid: a base traz os nomes das causas e o mínimo de óbitos", { bb <- base_sob_demanda(P, cid_nomes = ler_cid_nomes(raiz)); length(bb$meta$cid_nomes) > 100 && identical(bb$meta$cid_min, CID_MIN) && all(unlist(pl$cid) %in% names(bb$meta$cid_nomes)) })

# diagnósticos e sensibilidades (aba Diagnósticos e sensibilidades): "diag_<medida>" e "sens_<análise>_<medida>"
checar("dg: reconhece o ajuste principal e cada análise de sensibilidade, e só eles",
       identical(dg_do_id("diag_horas")$tipo, "diag") && identical(dg_do_id("diag_haat")$medida, "haat") && all(vapply(names(SENS), function(i) identical(dg_do_id(paste0("sens_", i, "_haat"))$spec, i), TRUE)) &&
         !any(vapply(c("diag", "diag_x", "diag_horas_", "sens_horas", "sens_xyz_horas", "sens_dow", "sens__haat", "Diag_horas", "diag_horas2"), function(x) !is.null(dg_do_id(x)), TRUE)) && is.null(dg_do_id(NA_character_)) && expo_valida("sens_k_meta_horas"))
dgp <- executar_ajuste(pasta, "res", chave, K, "diag_horas")
pdg <- json_de(dgp$payload); rrj <- json_de(r_nat)$rr
checar("diag: o RR é o do ajuste principal (mesmo modelo da Figura 1) e traz diagnóstico completo",
       identical(pdg$tipo, "diag") && !dgp$do_cache && abs(pdg$rr[[1]] - rrj[[1]]) < 1e-9 && abs(pdg$lo[[1]] - rrj[[2]]) < 1e-9 && abs(pdg$hi[[1]] - rrj[[3]]) < 1e-9 && abs(pdg$rr[[2]] - rrj[[4]]) < 1e-9 &&
         length(pdg$diag$acf) == ACF_MAX && length(pdg$diag$suaves) == 3 && !is.null(pdg$diag$covid_cc) && pdg$diag$conv$ok && is.null(pdg$cv))
checar("diag: dias, óbitos e eventos de calor batem com o resumo do ajuste", { a <- json_de(r_nat)$aj; pdg$nd == a$nd && pdg$no == a$no && pdg$dias_calor >= pdg$eventos && pdg$eventos > 0 && pdg$ini == a$ini && pdg$fim == a$fim })
checar("diag: o segundo pedido sai do disco", executar_ajuste(pasta, "res", chave, K, "diag_horas")$do_cache)
sn <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_ncmant_horas")$payload); r001 <- json_de(executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "001")$payload)$rr
checar("sens: 'meses mantidos' é o ajuste com código 001, com mais dias e óbitos que o principal",
       identical(sn$tipo, "sens") && abs(sn$rr[[1]] - r001[[1]]) < 1e-9 && abs(sn$hi[[2]] - r001[[6]]) < 1e-9 && sn$nd > pdg$nd && sn$no > pdg$no && !is.null(sn$res$lb_p) && is.null(sn$diag))
checar("sens: 'período da COVID-19 retirado' é o ajuste com código 111 e tem menos dias", { sc <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_covret_horas")$payload); r111 <- json_de(executar_ajuste(pasta, "res", chave, K, "horas", "naturais", "111")$payload)$rr
  abs(sc$rr[[1]] - r111[[1]]) < 1e-9 && sc$nd < pdg$nd })
checar("sens: a especificação anterior é o ajuste com código 000", { sa <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_anterior_horas")$payload); r000 <- json_de(r_000$payload)$rr; abs(sa$rr[[1]] - r000[[1]]) < 1e-9 && sa$nd == length(cx$dias) - sum(cx$sem_registro) })
checar("sens: cada análise tem o rótulo, o grupo, a defasagem e o número de nós do spline do tempo", { sl <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_lag14_horas")$payload); sk <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_k_dobro_horas")$payload)
  sl$lag == 14 && sl$grupo == "Defasagem" && sl$nd < pdg$nd && sk$k_tempo == 2 * P$kt && nzchar(sk$rot) })
checar("sens: especificação alternativa com HAAT (spline penalizado): RR nos dois níveis e gl efetivos da base cruzada", { sh <- json_de(executar_ajuste(pasta, "res", chave, K, "sens_dow_haat")$payload); length(sh$rr) == 2 && all(num(sh$lo) < num(sh$rr)) && sh$res$edf_cb > 5 && sh$res$edf_cb < 45 })
checar("dg: análise inexistente, medida errada ou recorte com poucos óbitos dão erro recorte_invalido",
       all(vapply(c("sens_xyz_horas", "sens_dow_mapa36", "diag_cid"), function(x) identical(cod(executar_ajuste(pasta, "res", chave, K, x)), "recorte_invalido"), TRUE)) && identical(cod(executar_ajuste(pasta, "res", chave, "Ignorado|30-39", "diag_horas")), "recorte_invalido"))
checar("base: traz a lista de análises de sensibilidade com rótulo e grupo", { bs <- base_sob_demanda(P)$meta$sens; length(bs) == length(SENS) && all(vapply(bs, function(z) all(c("id", "rot", "grupo") %in% names(z)), TRUE)) && setequal(vapply(bs, `[[`, "", "id"), names(SENS)) })

# forma da curva de exposição-resposta: "flex_horas" = reta imposta e curva flexível pré-definida no mesmo recorte
checar("flex: reconhece só flex_horas", identical(dg_do_id("flex_horas")$tipo, "flex") && expo_valida("flex_horas") && !any(vapply(c("flex_haat", "flex_", "flex", "flex_horas2", "Flex_horas"), function(x) expo_valida(x), TRUE)))
fxr <- executar_ajuste(pasta, "res", chave, K, "flex_horas"); fx <- json_de(fxr$payload)
checar("flex: a reta é o ajuste principal das horas (mesmo RR e IC da Figura 1) e RR(8 h) = RR(4 h)^2",
       identical(fx$tipo, "flex") && !fxr$do_cache && abs(fx$lin$rr[[1]] - rrj[[1]]) < 1e-9 && abs(fx$lin$lo[[1]] - rrj[[2]]) < 1e-9 && abs(fx$lin$hi[[2]] - rrj[[6]]) < 1e-9 &&
         abs(fx$lin$rr[[2]] - fx$lin$rr[[1]]^2) < 5e-4 && abs(fx$lin$r84[[1]] - fx$lin$rr[[1]]) < 5e-4)
checar("flex: curva flexível com 9 colunas, nós em 3 e 6 h, e a mesma grade de exposição da reta e da Figura 2",
       fx$flex$k == 9 && fx$flex$edf == 9 && fx$lin$k == 3 && all(unlist(fx$nos) == c(3, 6)) && length(fx$nos) == 2 && length(fx$flex$cv$x) == 41 && identical(unlist(fx$flex$cv$x), unlist(fx$lin$cv$x)) &&
         identical(unlist(fx$lin$cv$x), unlist(json_de(r_nat)$cv$x)) && all(unlist(fx$flex$cv$lo) <= unlist(fx$flex$cv$rr)) && all(unlist(fx$flex$cv$rr) <= unlist(fx$flex$cv$hi)))
checar("flex: comparação traz razão de desvios aproximada, ΔAIC e a razão dos log RR", { cc <- fx$comp; !is.null(cc$p) && cc$p >= 0 && cc$p <= 1 && cc$gl > 5 && cc$gl < 7 && is.finite(cc$d_aic) && is.finite(cc$razao) && abs(cc$d_aic - (fx$flex$aic - fx$lin$aic)) < 0.15 })
checar("flex: suporte de dados = dias no ajuste por hora, e soma o número de dias do ajuste", { a <- json_de(r_nat)$aj; sum(unlist(fx$sup$n)) == fx$nd && fx$nd == a$nd && fx$no == a$no && length(fx$sup$h) == length(fx$sup$n) && fx$sup$h[[1]] == 0 && fx$p99 > 0 })
checar("flex: o dia sem calor tem a maior contagem e as contagens batem com a série de horas dentro do ajuste", { f <- fora_ajuste(cx, opc_de_codigo(COD_PADRAO)); h0 <- P$b$num_hr_36[!f]; identical(as.integer(unlist(fx$sup$n)), as.integer(tabulate(floor(h0) + 1L, nbins = max(P$b$num_hr_36) + 1L))) })
checar("flex: o segundo pedido sai do disco", executar_ajuste(pasta, "res", chave, K, "flex_horas")$do_cache)
checar("flex: recorte com poucos óbitos dá recorte_invalido", identical(cod(executar_ajuste(pasta, "res", chave, "Ignorado|30-39", "flex_horas")), "recorte_invalido"))
checar("principal: o payload traz as colunas da base cruzada e os graus de liberdade efetivos", { a <- json_de(r_nat); a$cb$k == 3 && a$cb$edf == 3 })
checar("principal HAAT: base cruzada de 45 colunas com gl efetivos menores (penalização)", { ah <- json_de(executar_ajuste(pasta, "res", chave, K, "haat")$payload); ah$cb$k == 45 && ah$cb$edf > 5 && ah$cb$edf < 45 })

# suporte dos contrastes acumulados: "sup_<medida>", conferido contra uma contagem independente (laços explícitos) sobre as séries do cache
sup_ref <- function(x, fora, r, lag = LAG, dur = DURACOES) {
  n <- length(x); e <- x >= r; jan <- integer(length(dur)); ev <- integer(length(dur)); id_ev <- integer(n); atual <- 0L; ult <- -Inf
  for (t in seq_len(n)) if (e[t]) { if (t - ult > lag) atual <- atual + 1L; id_ev[t] <- atual; ult <- t }
  for (i in seq_along(dur)) { d <- dur[i]; ok <- logical(n); for (t in seq_len(n)) ok[t] <- t >= d && !fora[t] && all(e[(t - d + 1):t]); jan[i] <- sum(ok); ev[i] <- length(unique(id_ev[ok])) }
  list(janelas = jan, eventos = ev, dias = sum(e & !fora))
}
checar("sup: reconhece só sup_horas e sup_haat", identical(dg_do_id("sup_horas")$tipo, "sup") && identical(dg_do_id("sup_haat")$medida, "haat") && expo_valida("sup_haat") && !any(vapply(c("sup_", "sup", "sup_cid", "sup_horas2", "Sup_horas"), function(x) expo_valida(x), TRUE)))
KS <- "Todos os locais|Todas as idades"
for (m in c("horas", "haat")) {
  spr <- executar_ajuste(pasta, "res", chave, KS, paste0("sup_", m)); sp <- json_de(spr$payload); E <- EXPOSICOES[[m]]
  fo <- fora_ajuste(cx, opc_de_codigo(COD_PADRAO)); xx <- P$b[[E$var]]
  checar(sprintf("sup %s: janelas, eventos e dias expostos batem com a contagem independente nos dois níveis (%s)", m, paste(E$ref, collapse = " e ")),
         identical(sp$tipo, "sup") && sp$nd == sum(!fo) && all(unlist(sp$ref) == E$ref) && all(vapply(1:2, function(j) { b <- sup_ref(xx, fo, E$ref[j]); q <- sp$niveis[[j]]
           identical(as.integer(unlist(q$janelas)), b$janelas) && identical(as.integer(unlist(q$eventos)), b$eventos) && q$dias == b$dias }, TRUE)))
  checar(sprintf("sup %s: soma por ano e sequências por duração fecham com os totais", m), all(vapply(sp$niveis, function(q) sum(unlist(q$anual$dias)) == q$dias && sum(unlist(q$anual$jan11)) == unlist(q$janelas)[5] && length(unlist(q$duracao$n)) == 5, TRUE)))
}
checar("sup: o segundo pedido sai do disco, e o suporte muda com as retiradas (ajuste sem tirar dias sem clima tem mais janelas ou o mesmo número)",
       executar_ajuste(pasta, "res", chave, KS, "sup_horas")$do_cache && { s0 <- json_de(executar_ajuste(pasta, "res", chave, KS, "sup_horas", "naturais", "000")$payload); s1 <- json_de(executar_ajuste(pasta, "res", chave, KS, "sup_horas")$payload); s0$nd > s1$nd && s0$niveis[[1]]$dias >= s1$niveis[[1]]$dias })

# pedidos assíncronos pelo future: pedidos iguais compartilham a promessa e o resultado é o mesmo
suppressWarnings(future::plan("multisession", workers = 1))
p1 <- pedir_ajuste(raiz, pasta, "res", chave, "Via pública|60-69", "horas")                 # a primeira chamada sobe o trabalhador e cria o pedido
t_2 <- system.time(p2 <- pedir_ajuste(raiz, pasta, "res", chave, "Via pública|60-69", "horas"))[["elapsed"]]
checar("pedido igual em andamento não abre outro trabalho", t_2 < 0.5 && length(ls(.pendentes, all.names = TRUE)) == 1, sprintf("%.2f s, %d pendentes", t_2, length(ls(.pendentes, all.names = TRUE))))
res <- NULL; err <- NULL; res_b <- NULL
promises::then(p2, function(v) res_b <<- v)
promises::then(p1, function(v) res <<- v, function(e) err <<- e)
t0 <- Sys.time(); while (is.null(res) && is.null(err) && difftime(Sys.time(), t0, units = "secs") < 180) later::run_now(0.2)
checar("pedido assíncrono termina e traz o payload", !is.null(res) && is.null(err) && all(comparar(res$payload, "Via pública|60-69", "horas")), if (!is.null(err)) conditionMessage(err) else "")
res2 <- NULL; promises::then(pedir_ajuste(raiz, pasta, "res", chave, "Via pública|60-69", "horas"), function(v) res2 <<- v)
t0 <- Sys.time(); while (is.null(res2) && difftime(Sys.time(), t0, units = "secs") < 20) later::run_now(0.1)
checar("os dois pedidos iguais recebem o mesmo payload", !is.null(res_b) && identical(res_b$payload, res$payload))
checar("o mesmo pedido de novo sai do disco na hora", !is.null(res2) && res2$do_cache)
res3 <- NULL; err3 <- NULL
promises::then(pedir_ajuste(raiz, pasta, "res", chave, "Via pública|60-69", "horas", "externas", "110"), function(v) res3 <<- v, function(e) err3 <<- e)
t0 <- Sys.time(); while (is.null(res3) && is.null(err3) && difftime(Sys.time(), t0, units = "secs") < 180) later::run_now(0.2)
checar("pedido assíncrono com causa e retiradas termina e grava o ajuste", !is.null(res3) && is.null(err3) && !res3$do_cache && file.exists(arquivo_ajuste(pasta, chave, "res", "horas", "Via pública|60-69", "externas", "110")), if (!is.null(err3)) conditionMessage(err3) else "")
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
