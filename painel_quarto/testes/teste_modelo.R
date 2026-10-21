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
# forma da curva (horas): a reta imposta tem RR(8 h) = RR(4 h)^2 por construção; a curva flexível pré-definida não impõe isso
cbf <- cross_exposicao(b, EXPOSICAO_FLEX)
ok(ncol(cbi$m) == 3 && ncol(cbf$m) == 9 && identical(HORAS_NOS, c(3, 6)) && qr(cbind(cbf$m, cbi$m))$rank == 9, "curva flexível: 9 colunas (3 gl na exposição x 3 na defasagem) e a reta (3 colunas) está contida nela")
cmp <- comparar_flex(y, b, cbi, cbf, cx$sem_registro, kt)
ok(abs(cmp$lin$rr[2] - cmp$lin$rr[1]^2) < 5e-4, sprintf("reta imposta: RR(8 h) = RR(4 h)^2 (%.4f e %.4f^2 = %.4f)", cmp$lin$rr[2], cmp$lin$rr[1], cmp$lin$rr[1]^2))
ok(abs(cmp$lin$r84[1] - cmp$lin$rr[1]) < 5e-4, "reta imposta: o RR de 8 h contra 4 h é o RR de 4 h contra nenhuma exposição")
ok(cmp$lin$k == 3 && cmp$lin$edf == 3 && cmp$flex$k == 9 && cmp$flex$edf == 9, "graus de liberdade da base cruzada: reta 3, curva flexível 9 (sem penalização)")
ok(length(cmp$flex$cv$x) == length(cmp$lin$cv$x) && all(cmp$flex$cv$x == cmp$lin$cv$x), "reta e curva flexível usam a mesma grade de exposição")
rr_verd8 <- exp(0.012 * 8 * 4)
ok(cmp$flex$lo[2] < rr_verd8 && rr_verd8 < cmp$flex$hi[2] && cmp$flex$lo[1] < rr_verd && rr_verd < cmp$flex$hi[1], "com efeito linear verdadeiro, o IC da curva flexível cobre o RR verdadeiro de 4 e de 8 h")
ok(abs(cmp$comp$razao - 2) < 0.6, sprintf("com efeito linear verdadeiro, log RR(8 h) / log RR(4 h) da curva flexível fica perto de 2 (%.2f)", cmp$comp$razao))
# efeito verdadeiro com patamar: o risco sobe até 3 h e fica estável; a reta não consegue descrever isso e a curva flexível sim
set.seed(7)
mu_pat <- exp(log_mu0 + 0.05 * rowSums(sapply(0:3, function(l) c(rep(0, l), pmin(h, 3)[seq_len(n - l)]))))
yp <- rnbinom(n, mu = mu_pat, size = 80)
cmpp <- comparar_flex(yp, b, cbi, cbf, cx$sem_registro, kt)
ok(cmpp$flex$rr[2] < 1.1 * cmpp$flex$rr[1] && cmpp$lin$rr[2] > 1.15 * cmpp$flex$rr[2], sprintf("com patamar verdadeiro, a curva flexível dá RR(8 h) = %.3f perto de RR(4 h) = %.3f e a reta superestima RR(8 h) (%.3f)", cmpp$flex$rr[2], cmpp$flex$rr[1], cmpp$lin$rr[2]))
ok(!is.null(cmpp$comp$p) && cmpp$comp$p < 0.01 && cmpp$comp$d_aic < 0 && cmpp$comp$razao < 1.3, sprintf("com patamar verdadeiro, o teste aproximado (p = %.2g) e o AIC (%.1f) preferem a curva flexível", cmpp$comp$p, cmpp$comp$d_aic))
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
# motivo de cada dia fora do ajuste e resumo do ajuste (ordem: sem registro, clima, nc, covid; cada dia conta uma vez)
cx3$clima$hi_max[c(100, 101, 195)] <- NA
mt <- motivo_fora(cx3, list(covid = TRUE, nc = TRUE, clima = TRUE))
ok(identical(which(!is.na(mt)), which(fora_ajuste(cx3, list(covid = TRUE, nc = TRUE, clima = TRUE)))) && mt[5] == "sem_registro" && mt[20] == "covid" && mt[60] == "nc" && mt[100] == "clima" && mt[111] == "clima" && is.na(mt[112]), "motivo de cada dia fora do ajuste")
y3 <- rep(2L, n3)
ra <- resumo_ajuste(cx3, y3, list(covid = TRUE, nc = TRUE, clima = TRUE))
ok(identical(as.integer(ra$xd), c(1L, 18L, 11L, 21L)) && identical(as.integer(ra$xo), c(2L, 36L, 22L, 42L)) && ra$ini == "2020-01-01" && ra$fim == as.character(d3[194]), "resumo do ajuste: contagens por motivo e primeiro e último dia no ajuste")
ok(ra$nd == n3 - 1L - 18L - 11L - 21L && ra$no == 2L * ra$nd, "resumo do ajuste: dias e óbitos no ajuste")
ok(identical(strsplit(COD_PADRAO, "")[[1]], c("0", "1", "1")), "ajuste principal: retira meses não consolidados e dias sem clima, mantém o período da COVID-19 (código covid-nc-clima = 011)")
# janela de defasagem parametrizável: a retirada dos dias sem clima e a cross-basis usam a mesma janela
cx3$clima$hi_max <- 30; cx3$clima$hi_max[c(100, 101, 195)] <- NA
ok(identical(which(fora_ajuste(cx3, list(clima = TRUE), lag = 3) & !cx3$sem_registro), c(100:104, 195:198)), "retirada de dias sem clima com defasagem de 3 dias: o dia e os 3 seguintes")
cbi7 <- cross_exposicao(b, EXPOSICOES$horas, lag = 7)
ok(nrow(cbi7$m) == n && ncol(cbi7$m) == 3 && cbi7$lag == 7 && all(cbi7$c0 == 0), "cross-basis com defasagem de 7 dias: mesma dimensão, contrafactual zero")
r7 <- ajustar_segmento(y, b, cbi7, cx$sem_registro, kt, curvas = FALSE)
ok(is.null(r7$curvas) && r7$rr["lo", 1] < exp(0.012 * 4 * 4) && exp(0.012 * 4 * 4) < r7$rr["hi", 1], "defasagem de 7 dias, sem as curvas: RR verdadeiro dentro do IC")

# diagnósticos: ACF dos resíduos, Ljung-Box, k.check, gl efetivos, dispersão e convergência
rd <- ajustar_segmento(y0, b, cbi, cx$sem_registro, kt, diag = "completo")
d <- rd$diag
ok(length(d$acf) == ACF_MAX && d$n == n && abs(d$lim - 1.96 / sqrt(n)) < 1e-3 && d$n_acf <= 6 && d$lb$gl == LB_LAGS, sprintf("diagnóstico: ACF de %d defasagens; com resíduos independentes, %d fora do limite", ACF_MAX, d$n_acf))
ok(abs(d$chi2_gl - 1) < 0.1 && d$conv$ok && is.finite(d$cb$edf) && d$cb$k == 3 && abs(d$cb$edf - 3) < 1e-6, "diagnóstico: dispersão residual perto de 1, convergência e base cruzada com 3 colunas e 3 gl efetivos")
ok(length(d$suaves) == 2 && all(vapply(d$suaves, function(z) is.finite(z$kindex) && z$k > 0 && z$edf > 0, TRUE)) && is.null(d$covid_cc), "diagnóstico completo: k.check dos dois termos suaves (sem o termo da COVID-19, que não há no ajuste)")
ok(is.null(ajustar_segmento(y0, b, cbi, cx$sem_registro, kt, diag = "resumo")$diag$suaves) && !is.null(ajustar_segmento(y0, b, cbi, cx$sem_registro, kt, diag = "resumo")$diag$lb), "diagnóstico resumido: sem k.check")
y_ar <- rnbinom(n, mu = exp(log_mu0 + as.numeric(arima.sim(list(ar = 0.9), n, sd = 0.06))), size = 80)
da <- ajustar_segmento(y_ar, b, cbi, cx$sem_registro, kt, diag = "resumo")$diag
ok(da$rho1 > 0.3 && da$lb$p < 1e-6 && da$n_acf > 15, sprintf("diagnóstico: variação autocorrelada que o modelo não descreve aparece na ACF (lag 1 = %.2f, %d lags fora) e no Ljung-Box", da$rho1, da$n_acf))
ok(all(c("lb_p", "n_acf", "rho1", "chi2_gl", "edf_cb") %in% names(resumo_residual(da))), "resumo do diagnóstico residual para o quadro de sensibilidades")

# análises de sensibilidade: especificações alternativas do GAM
rdw <- ajustar_segmento(y0, b, cbi, cx$sem_registro, kt, esp = list(dow = TRUE), curvas = FALSE)
ok(abs(log(rdw$rr["rr", 1]) - log(r0$rr["rr", 1])) < 0.02, "sensibilidade com dia da semana: sem efeito de dia da semana nos dados, o RR quase não muda")
rs <- ajustar_segmento(y0, b, cbi, cx$sem_registro, kt, esp = list(covid = "sem"), curvas = FALSE)
ok(isTRUE(all.equal(rs$rr, r0$rr)), "termo da COVID-19 'sem': sem período de COVID-19 no ajuste, igual ao modelo de referência")
cxc <- cx; cxc$covid[(n - 900):(n - 300)] <- TRUE
bc <- base_modelo(cxc); m_c <- sum(cxc$covid)
yc <- rnbinom(n, mu = mu_verd * exp(ifelse(cxc$covid, 0.35 * sin(pi * cumsum(cxc$covid) / m_c), 0)), size = 80)
dc <- ajustar_segmento(yc, bc, cbi, cxc$sem_registro, kt, diag = "completo", curvas = FALSE)$diag
ok(length(dc$suaves) == 3 && !is.null(dc$covid_cc) && abs(dc$covid_cc$ultimo - dc$covid_cc$fora) < 0.01 && abs(dc$covid_cc$pico) > 0.1,
   sprintf("spline cíclico da pandemia: o valor no último dia (%.3f) volta ao de fora do período (%.3f), com pico de %.2f", dc$covid_cc$ultimo, dc$covid_cc$fora, dc$covid_cc$pico))
ncc <- ajustar_segmento(yc, bc, cbi, cxc$sem_registro, kt, esp = list(covid = "cr"), curvas = FALSE)
ok(ncc$rr["lo", 1] < exp(0.012 * 4 * 4) && exp(0.012 * 4 * 4) < ncc$rr["hi", 1], "termo da COVID-19 não cíclico com indicador do período: RR verdadeiro dentro do IC")
bc$covid_obs <- log1p(as.numeric(stats::filter(ifelse(cxc$covid, 20 * sin(pi * cumsum(cxc$covid) / m_c), 0), rep(1 / 7, 7), sides = 1)) |> (\(v) { v[is.na(v)] <- 0; v })())
nob <- ajustar_segmento(yc, bc, cbi, cxc$sem_registro, kt, esp = list(covid = "obs"), curvas = FALSE)
ok(nob$rr["lo", 1] < exp(0.012 * 4 * 4) && exp(0.012 * 4 * 4) < nob$rr["hi", 1], "termo da COVID-19 pelos óbitos diários de COVID-19: RR verdadeiro dentro do IC")
nc <- contagem_calor(list(clima = data.frame(num_hr_36 = c(0, 5, 6, 0, 4, NA, 7, 7, 7, 1))), c(rep(FALSE, 8), TRUE, FALSE))
ok(nc$dias == 5 && nc$eventos == 3, "dias de calor (>= 4 h) e eventos (sequências) dentro do ajuste")
ok(all(vapply(SENS, function(z) is.character(z$rot) && is.character(z$grupo), TRUE)) && length(SENS) == 12, "lista de sensibilidades com rótulo e grupo")

cat("\nTodos os testes do modelo passaram.\n")
