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
cat("\nTodos os testes do modelo passaram.\n")
