# Modelo do João (GAM + DLNM) aplicado a cada segmento da Figura 1.
#
# Para cada série diária de óbitos por causas naturais (local x faixa etária, ou local x raça/cor):
#   y_t ~ NB(mu_t),  log(mu_t) = cross-basis(calor, defasagem 0 a 10) + s(tempo) + s(dia do ano, cíclico) + s(período COVID, cíclico)
# estimado com mgcv::gam (REML). A cross-basis é a do dlnm: função da exposição (ns com 1 gl para horas; spline penalizado com 15 gl para o HAAT)
# x função da defasagem (ns com 3 gl). Os termos suaves e as dimensões seguem o script 02_model_fitting.R do João, com um ajuste: a série
# aqui tem mais anos, então o número de nós do spline de tempo cresce na mesma proporção (12 nós para 12,5 anos).
#
# Esperado sem calor (contrafactual): o preditor linear do modelo com a cross-basis trocada pela exposição zero, em cada dia.
# Dias sem registro no SIM saem do ajuste (resposta ausente); dias de COVID ficam e o termo s(covid_id) absorve o período.
# Não há termo de dia da semana, como no modelo do João (o dia da semana foi uma análise de sensibilidade à parte).

suppressPackageStartupMessages({ library(mgcv); library(dlnm) })

LAG <- 10
K_REF <- 12; ANOS_REF <- 12.5
EXPOSICOES <- list(
  horas = list(nome = "Horas por dia com índice de calor ≥ 36 °C", var = "num_hr_36", fun = "ns", df = 1,  ref = c(4, 8),  unidade = "h"),
  haat  = list(nome = "HAAT: graus-hora acima de 36 °C no dia",    var = "auc36",     fun = "ps", df = 15, ref = c(5, 20), unidade = "°C·h"))

# Calendário do modelo: tempo, dia do ano, índice do período COVID e as exposições (dia sem dado de clima = dia sem calor)
base_modelo <- function(cx) {
  n <- length(cx$dias)
  b <- data.frame(dia = cx$dias, time_id = seq_len(n), dia_ano = as.POSIXlt(cx$dias)$yday + 1L)
  b$covid_id <- 0L; b$covid_id[cx$covid] <- seq_len(sum(cx$covid))
  for (e in EXPOSICOES) { x <- cx$clima[[e$var]]; x[is.na(x)] <- 0; b[[e$var]] <- x }
  b
}

k_tempo <- function(n_dias) max(round(K_REF * n_dias / (ANOS_REF * 365.25)), 6)

# Cross-basis de uma exposição. Os 10 dias anteriores ao início entram como dia sem calor, para a cross-basis valer desde o primeiro dia.
# Guarda também a linha da cross-basis para exposição zero em todas as defasagens (c0), usada no contrafactual.
cross_exposicao <- function(b, e) {
  x <- b[[e$var]]
  cb <- crossbasis(c(rep(0, LAG), x), lag = LAG, argvar = list(fun = e$fun, df = e$df), arglag = list(fun = "ns", df = 3))
  m <- matrix(as.numeric(cb[-seq_len(LAG), , drop = FALSE]), nrow = length(x), dimnames = list(NULL, colnames(cb)))
  nz <- cumsum(x != 0); janela_com_calor <- nz - c(rep(0, LAG + 1), head(nz, -(LAG + 1)))
  i0 <- which(seq_along(x) > LAG & janela_com_calor == 0)[1]
  stopifnot(!is.na(i0))
  list(obj = cb, m = m, c0 = m[i0, ], pen = if (e$fun == "ps") cbPen(cb) else NULL, e = e)
}

# Ajusta um segmento. y = óbitos por dia (calendário completo); fora = dias fora do ajuste (sem registro no SIM).
# Devolve a família usada, o RR acumulado nas exposições de referência e os vetores diários (NA fora do ajuste).
ajustar_segmento <- function(y, b, cbi, fora, k_time) {
  dd <- b; dd$y <- y; dd$y[fora] <- NA
  cb_i <- cbi$m
  pen <- if (is.null(cbi$pen)) NULL else list(cb_i = cbi$pen)
  fm <- if (any(dd$covid_id[!is.na(dd$y)] > 0))
    y ~ cb_i + s(time_id, k = k_time, bs = "tp") + s(dia_ano, k = 6, bs = "cc") + s(covid_id, k = 8, bs = "cc")
  else                                                               # série sem dias de COVID no ajuste (só em dados de teste): sem o termo
    y ~ cb_i + s(time_id, k = k_time, bs = "tp") + s(dia_ano, k = 6, bs = "cc")
  fam <- "nb"
  fit <- tryCatch(suppressWarnings(gam(fm, data = dd, family = nb(), paraPen = pen, method = "REML")), error = function(e) NULL)
  if (is.null(fit) || !isTRUE(fit$converged)) {                      # séries muito esparsas: quase-Poisson (a dispersão entra no lugar de theta)
    fit <- suppressWarnings(gam(fm, data = dd, family = quasipoisson(), paraPen = pen, method = "REML")); fam <- "qp"
  }
  ok <- !is.na(dd$y)
  stopifnot(length(fit$y) == sum(ok))
  ib <- grep("^cb_i", names(coef(fit)))
  beta <- coef(fit)[ib]
  efeito <- as.numeric(cb_i %*% beta) - sum(cbi$c0 * beta)             # log do efeito do calor em cada dia do calendário
  eta <- rep(NA_real_, nrow(dd)); eta[ok] <- as.numeric(predict(fit, type = "link"))
  pr <- crosspred(cbi$obj, coef = beta, vcov = vcov(fit)[ib, ib], model.link = "log", at = cbi$e$ref, cen = 0)
  disp <- if (fam == "nb") fit$family$getTheta(TRUE) else fit$scale   # theta (NB: var = mu + mu^2/theta) ou φ (var = φ mu)
  list(fam = fam, disp = disp, n = sum(dd$y[ok]),
       rr = rbind(rr = pr$allRRfit, lo = pr$allRRlow, hi = pr$allRRhigh),
       mu_ajustado = exp(eta), mu_sem_calor = exp(eta - efeito), efeito = efeito,
       dev_expl = summary(fit)$dev.expl)
}

# Variância de um dia sob o modelo
var_dia <- function(mu, fam, disp) if (fam == "nb") mu + mu^2 / disp else disp * mu

# Esperado semanal = soma dos esperados diários da semana (só semanas com os 7 dias no ajuste).
# Faixa de 95%: aproximação normal com a soma das variâncias diárias do modelo, multiplicada por uma dispersão semanal phi (>= 1) estimada nos
# resíduos de Pearson semanais do modelo ajustado (com o calor). Dias vizinhos têm resíduos correlacionados (epidemias e outros eventos que o
# modelo não descreve), e a soma de variâncias independentes subestima a variância semanal; phi corrige isso. `excluir` = semanas fora da estimativa de phi (COVID).
# A faixa não inclui a incerteza dos coeficientes.
semanal <- function(r, y, sem, excluir = NULL) {
  g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
  mu    <- tapply(r$mu_sem_calor, g, sum)                              # NA se algum dia da semana ficou fora do ajuste
  mu_aj <- tapply(r$mu_ajustado, g, sum)
  v     <- tapply(var_dia(r$mu_sem_calor, r$fam, r$disp), g, sum)
  v_aj  <- tapply(var_dia(r$mu_ajustado, r$fam, r$disp), g, sum)
  o     <- tapply(y, g, sum)
  uso <- !is.na(mu_aj) & !(if (is.null(excluir)) FALSE else excluir)
  phi <- max(1, mean(((o - mu_aj)^2 / v_aj)[uso]))
  sd <- sqrt(phi * v)
  list(o = as.integer(o), e = as.numeric(mu), l = as.numeric(pmax(mu - 1.96 * sd, 0)), u = as.numeric(mu + 1.96 * sd), phi = phi)
}
