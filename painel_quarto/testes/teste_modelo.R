# Teste do modelo do João com dados simulados de efeito conhecido. Uso: Rscript testes/teste_modelo.R (a partir da pasta do projeto)
# Os rótulos têm acento: garante locale UTF-8 antes de ler o resto do script (em sessões com locale "C" os literais seriam lidos como bytes soltos)
if (!l10n_info()[["UTF-8"]]) suppressWarnings(try(Sys.setlocale("LC_ALL", "C.UTF-8"), silent = TRUE))
raiz <- if (file.exists("R/funcoes.R")) "." else ".."
source(file.path(raiz, "R/utf8.R")); fonte_utf8(file.path(raiz, "R/funcoes.R")); fonte_utf8(file.path(raiz, "R/modelo_joao.R"))
ok <- function(cond, msg) { if (!isTRUE(cond)) stop("FALHOU: ", msg, call. = FALSE); cat("ok  ", msg, "\n") }

set.seed(42)
dias <- seq(as.Date("2012-01-01"), as.Date("2017-12-31"), by = "day"); n <- length(dias)
doy <- as.POSIXlt(dias)$yday
# horas de índice de calor >= 36 °C: só no verão, em sequências de dias
h <- pmax(0, round(rnorm(n, 5 * pmax(0, cos(2 * pi * (doy - 20) / 365.25)) - 1.5, 2.5)))
cx <- list(dias = dias, covid = rep(FALSE, n), sem_registro = rep(FALSE, n),
           clima = data.frame(dia = dias, num_hr_36 = h, auc36 = 0.5 * h^1.2))
# efeito verdadeiro: cada hora de calor eleva o risco em 1,2% nas defasagens 0 a 3 (efeito acumulado de 4 h por dia sustentado nos 11 dias: exp(0,012*4*4))
lagged <- sapply(0:3, function(l) c(rep(0, l), h[seq_len(n - l)]))
log_mu0 <- log(60) + 0.0003 * seq_len(n) / 30 + 0.15 * cos(2 * pi * (doy - 20) / 365.25)
mu_verd <- exp(log_mu0 + 0.012 * rowSums(lagged))
y <- rnbinom(n, mu = mu_verd, size = 80)

b <- base_modelo(cx); kt <- k_tempo(n)
cbi <- cross_exposicao(b, EXPOSICOES$horas)
ok(all(cbi$c0 == 0), "cross-basis da exposição zero é zero para horas (ns de 1 gl)")
r <- ajustar_segmento(y, b, cbi, cx$sem_registro, kt)
rr_verd <- exp(0.012 * 4 * 4)                       # RR acumulado com 4 h sustentadas em lags 0 a 3
ok(r$fam == "nb", "binomial negativa converge")
ok(r$rr["lo", 1] < rr_verd && rr_verd < r$rr["hi", 1], sprintf("RR verdadeiro (%.3f) dentro do IC estimado (%.3f a %.3f)", rr_verd, r$rr["lo", 1], r$rr["hi", 1]))
ok(abs(r$disp - 80) / 80 < 0.5, sprintf("theta estimado (%.0f) perto do verdadeiro (80)", r$disp))
# contrafactual: ajustado / sem calor = exp(efeito do calor); a soma da diferença é o excesso atribuível
ok(max(abs(r$mu_ajustado / r$mu_sem_calor - exp(r$efeito))) < 1e-8, "ajustado ÷ esperado sem calor = exp(efeito do calor) em cada dia")
ok(all(abs(r$efeito[h == 0 & c(0, h[-n]) == 0 & c(0, 0, h[seq_len(n - 2)]) == 0 & c(0, 0, 0, h[seq_len(n - 3)]) == 0]) < 0.05), "dias sem calor nas últimas defasagens quase não têm efeito")
exc_est <- sum(r$mu_ajustado - r$mu_sem_calor); exc_verd <- sum(mu_verd - exp(log_mu0))
ok(abs(exc_est - exc_verd) / exc_verd < 0.15, sprintf("excesso atribuível estimado (%.0f) perto do verdadeiro (%.0f)", exc_est, exc_verd))
# sem efeito: o IC do RR cobre 1
y0 <- rnbinom(n, mu = exp(log_mu0), size = 80)
r0 <- ajustar_segmento(y0, b, cbi, cx$sem_registro, kt)
ok(r0$rr["lo", 1] < 1 && 1 < r0$rr["hi", 1], sprintf("sem efeito verdadeiro, o IC cobre 1 (%.3f a %.3f)", r0$rr["lo", 1], r0$rr["hi", 1]))
# dias sem registro saem do ajuste e ficam sem esperado na soma semanal
fora <- rep(FALSE, n); fora[100:120] <- TRUE
rf <- ajustar_segmento(y, b, cbi, fora, kt)
sem <- semanas(dias)
w <- semanal(rf, y, sem)
ok(all(is.na(rf$mu_sem_calor[fora])) && !anyNA(rf$mu_sem_calor[!fora]), "dias fora do ajuste ficam sem esperado; os demais têm esperado")
sem_fora <- tapply(fora, factor(as.character(sem$ini), levels = as.character(sem$ini_ok)), any)
ok(identical(unname(is.na(w$e)), unname(as.logical(sem_fora))), "semana com algum dia fora do ajuste fica sem esperado semanal")
ok(all(w$l <= w$e | is.na(w$e)) && all(w$e <= w$u | is.na(w$e)), "faixa semanal envolve o esperado")
# HAAT (spline penalizado): contrafactual com cross-basis zero não-nula, mesmo assim sem calor <= ajustado
cbh <- cross_exposicao(b, EXPOSICOES$haat)
rh <- ajustar_segmento(y, b, cbh, cx$sem_registro, kt)
ok(is.finite(rh$rr[1, 1]) && rh$rr[1, 1] > 1, sprintf("HAAT: RR acumulado com 5 °C·h acima de 1 (%.3f)", rh$rr[1, 1]))
# mapa de horas por dia x limiar: com efeito verdadeiro, as células com dias suficientes têm RR acima de 1; sem efeito, o IC cobre 1
mp <- ajustar_mapa_limiar(y, b, h, cx$sem_registro, kt, 36, horas = c(1, 2, 4, 8, 100))
ok(identical(mp$tipo, "mapa") && mp$limiar == 36 && length(mp$rr) == 5, "mapa: a coluna traz o limiar e uma célula por nível de horas")
ok(all(mp$nd == c(sum(h >= 1), sum(h >= 2), sum(h >= 4), sum(h >= 8), 0)), "mapa: dias expostos = dias com pelo menos H horas")
ok(is.na(mp$rr[5]) && !anyNA(mp$rr[1:3]) && all(mp$lo[1:3] > 1), sprintf("mapa: com efeito verdadeiro, RR acima de 1 com IC acima de 1 (%.3f, %.3f, %.3f); sem dias expostos, sem estimativa", mp$rr[1], mp$rr[2], mp$rr[3]))
mp0 <- ajustar_mapa_limiar(y0, b, h, cx$sem_registro, kt, 36, horas = c(1, 2, 4))
ok(all(mp0$lo < 1 & mp0$hi > 1), sprintf("mapa: sem efeito verdadeiro, os IC cobrem 1 (%.3f a %.3f com H = 1)", mp0$lo[1], mp0$hi[1]))
ok(identical(limiar_do_id("mapa36"), 36L) && is.na(limiar_do_id("mapa31")) && is.na(limiar_do_id("horas")) && is.na(limiar_do_id("mapa036")), "mapa: id do pedido -> limiar (32 a 44)")
fora_m <- rep(FALSE, n); fora_m[which(h >= 4)] <- TRUE                    # todos os dias expostos fora do ajuste
ok(is.na(ajustar_mapa_limiar(y, b, h, fora_m, kt, 36, horas = 4)$rr), "mapa: dias expostos fora do ajuste não contam (célula sem estimativa)")
# fora_ajuste(): o que cada caixa de "retirar do ajuste" tira
d3 <- seq(as.Date("2020-01-01"), by = "day", length.out = 200); n3 <- length(d3)
cx3 <- list(dias = d3, sem_registro = rep(FALSE, n3), covid = rep(FALSE, n3), nao_consolidado = rep(FALSE, n3), clima = data.frame(dia = d3, hi_max = rep(30, n3)))
cx3$sem_registro[5] <- TRUE; cx3$covid[20:40] <- TRUE; cx3$nao_consolidado[60:70] <- TRUE; cx3$clima$hi_max[c(100, 101, 195)] <- NA
f <- function(...) fora_ajuste(cx3, modifyList(list(covid = FALSE, nc = FALSE, clima = FALSE), list(...)))
ok(identical(f(), cx3$sem_registro), "retiradas: sem nenhuma caixa, só os dias sem registro saem do ajuste")
ok(identical(f(covid = TRUE), cx3$sem_registro | cx3$covid), "retiradas: período COVID")
ok(identical(f(nc = TRUE), cx3$sem_registro | cx3$nao_consolidado), "retiradas: meses não consolidados")
fc <- f(clima = TRUE)
ok(identical(which(fc & !cx3$sem_registro), c(100:111, 195:200)), "retiradas: dia sem clima e os dez seguintes, até o fim da série")
ok(identical(f(covid = TRUE, nc = TRUE, clima = TRUE), cx3$sem_registro | cx3$covid | cx3$nao_consolidado | fc), "retiradas: as três juntas somam os dias retirados")
cx3$clima$hi_max <- 30
ok(identical(fora_ajuste(cx3, list(clima = TRUE)), cx3$sem_registro), "retiradas: sem dia sem clima, a caixa não tira nada")
cat("\nTodos os testes do modelo passaram.\n")
