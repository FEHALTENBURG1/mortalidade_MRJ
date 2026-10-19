# Modelo de referência (GAM + DLNM, adaptado de Morais et al.) aplicado a cada segmento da Figura 1.
#
# Para cada série diária de óbitos por causas naturais (local x faixa etária, ou local x raça/cor):
#   y_t ~ NB(mu_t),  log(mu_t) = cross-basis(calor, defasagem 0 a 10) + s(tempo) + s(dia do ano, cíclico) + s(período COVID, cíclico)
# estimado com mgcv::gam (REML). A cross-basis é a do dlnm: função da exposição (ns com 1 gl para horas; spline penalizado com 15 gl para o HAAT)
# x função da defasagem (ns com 3 gl). Os termos suaves e as dimensões seguem o script 02_model_fitting.R de Morais et al., com um ajuste: a série
# aqui tem mais anos, então o número de nós do spline de tempo cresce na mesma proporção (12 nós para 12,5 anos).
#
# Esperado sem calor (contrafactual): o preditor linear do modelo com a cross-basis trocada pela exposição zero, em cada dia.
# Dias sem registro no SIM saem do ajuste (resposta ausente); dias de COVID ficam e o termo s(covid_id) absorve o período.
# Não há termo de dia da semana, como no modelo de referência (o dia da semana foi uma análise de sensibilidade à parte).

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

# Dias fora do ajuste (resposta ausente). Sempre saem os dias sem registro no SIM. Opcionalmente, e na ordem das caixas do app:
#   covid = os dias do período COVID (sem eles, o termo suave do período some do modelo);
#   nc    = os dias de meses com registro não consolidado;
#   clima = os dias sem dado de clima e os LAG dias seguintes (a cross-basis deles dependeria de exposição ausente).
# opc: list(covid, nc, clima) de TRUE/FALSE. Sem opc, só os dias sem registro (o que a Figura 1 em Quarto faz).
fora_ajuste <- function(cx, opc = list(covid = FALSE, nc = FALSE, clima = FALSE)) {
  fora <- cx$sem_registro
  if (isTRUE(opc$covid)) fora <- fora | cx$covid
  if (isTRUE(opc$nc)) fora <- fora | cx$nao_consolidado
  if (isTRUE(opc$clima)) {
    sem <- which(is.na(cx$clima$hi_max)); n <- length(fora)
    fora[unique(pmin(rep(sem, each = LAG + 1) + 0:LAG, n))] <- TRUE
  }
  fora
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

# Curvas do modelo para a aba de exposição-resposta, a partir dos coeficientes da cross-basis (beta) e da sua matriz de covariância (V):
#   x, rr, lo, hi: RR acumulado em 0 a LAG dias para uma exposição x mantida em todos os dias, em relação a x = 0 (grade de 41 pontos até o percentil 99 dos dias com exposição, porque acima disso há poucos dias);
#   lag: para cada nível de referência, o RR em cada defasagem (rr, lo, hi) e o RR acumulado até cada defasagem (ac, aclo, achi).
curvas_modelo <- function(cbi, beta, V, x_max) {
  e <- cbi$e
  grade <- seq(0, x_max, length.out = 41)
  at <- sort(unique(c(grade, e$ref)))
  pr <- crosspred(cbi$obj, coef = beta, vcov = V, model.link = "log", at = at, cen = 0, cumul = TRUE)
  i_g <- match(round(grade, 8), round(pr$predvar, 8))
  nivel <- lapply(e$ref, function(r) {
    i <- which.min(abs(pr$predvar - r))
    list(ref = r, rr = pr$matRRfit[i, ], lo = pr$matRRlow[i, ], hi = pr$matRRhigh[i, ],
         ac = pr$cumRRfit[i, ], aclo = pr$cumRRlow[i, ], achi = pr$cumRRhigh[i, ])
  })
  list(x = grade, rr = pr$allRRfit[i_g], lo = pr$allRRlow[i_g], hi = pr$allRRhigh[i_g], lag = nivel)
}

# Ajuste do modelo de referência (gam do mgcv, REML) para uma cross-basis `cb_i` (matriz do calendário) e os dados `dd` (colunas y, time_id, dia_ano, covid_id).
# Usa a negativa binomial e, se ela não convergir (séries muito esparsas), a quase-Poisson (a dispersão entra no lugar de theta).
# `pen` = list(cb_i = matriz de penalização) para o spline penalizado do HAAT, ou NULL. Devolve list(fit, fam) com fam "nb" ou "qp".
ajustar_gam <- function(dd, cb_i, pen, k_time) {
  fm <- if (any(dd$covid_id[!is.na(dd$y)] > 0))
    y ~ cb_i + s(time_id, k = k_time, bs = "tp") + s(dia_ano, k = 6, bs = "cc") + s(covid_id, k = 8, bs = "cc")
  else                                                               # série sem dias de COVID no ajuste (só em dados de teste): sem o termo
    y ~ cb_i + s(time_id, k = k_time, bs = "tp") + s(dia_ano, k = 6, bs = "cc")
  fam <- "nb"
  fit <- tryCatch(suppressWarnings(gam(fm, data = dd, family = nb(), paraPen = pen, method = "REML")), error = function(e) NULL)
  if (is.null(fit) || !isTRUE(fit$converged)) {
    fit <- suppressWarnings(gam(fm, data = dd, family = quasipoisson(), paraPen = pen, method = "REML")); fam <- "qp"
  }
  list(fit = fit, fam = fam)
}

# Ajusta um segmento. y = óbitos por dia (calendário completo); fora = dias fora do ajuste (sem registro no SIM).
# Devolve a família usada, o RR acumulado nas exposições de referência e os vetores diários (NA fora do ajuste).
ajustar_segmento <- function(y, b, cbi, fora, k_time) {
  dd <- b; dd$y <- y; dd$y[fora] <- NA
  cb_i <- cbi$m
  g <- ajustar_gam(dd, cb_i, if (is.null(cbi$pen)) NULL else list(cb_i = cbi$pen), k_time)
  fit <- g$fit; fam <- g$fam
  ok <- !is.na(dd$y)
  stopifnot(length(fit$y) == sum(ok))
  ib <- grep("^cb_i", names(coef(fit)))
  beta <- coef(fit)[ib]
  efeito <- as.numeric(cb_i %*% beta) - sum(cbi$c0 * beta)             # log do efeito do calor em cada dia do calendário
  eta <- rep(NA_real_, nrow(dd)); eta[ok] <- as.numeric(predict(fit, type = "link"))
  V <- vcov(fit)[ib, ib]
  pr <- crosspred(cbi$obj, coef = beta, vcov = V, model.link = "log", at = cbi$e$ref, cen = 0)
  disp <- if (fam == "nb") fit$family$getTheta(TRUE) else fit$scale   # theta (NB: var = mu + mu^2/theta) ou φ (var = φ mu)
  list(fam = fam, disp = disp, n = sum(dd$y[ok]),
       rr = rbind(rr = pr$allRRfit, lo = pr$allRRlow, hi = pr$allRRhigh),
       curvas = curvas_modelo(cbi, beta, V, ceiling(quantile(b[[cbi$e$var]][b[[cbi$e$var]] > 0], 0.99))),
       mu_ajustado = exp(eta), mu_sem_calor = exp(eta - efeito), efeito = efeito,
       dev_expl = summary(fit)$dev.expl)
}

# ---------------------------------------------------------------- mapa de horas por dia x limiar do índice de calor (Figura 4)
# Cada célula é um modelo próprio, com o mesmo GAM e a mesma defasagem (0 a LAG dias) do modelo de referência, mas com a exposição binária
#   x_t = 1 se o dia t tem pelo menos H horas com índice de calor >= K °C (dia sem dado de clima = 0).
# A cross-basis é linear na exposição (um coeficiente por termo da defasagem) e o RR é o acumulado em 0 a LAG dias de x = 1 contra x = 0.
# As células são independentes e não há correção para comparações múltiplas; o mapa é descritivo.
LIMIARES <- 32:44
HORAS_MAPA <- c(1, 2, 3, 4, 6, 8, 10, 12)
MIN_DIAS_EXPOSTOS <- 15                     # célula com menos dias expostos no ajuste, ou com menos de 30 dias sem exposição, não é estimada

# Identificador de pedido do mapa ("mapa36") -> limiar 36; NA se não for um limiar do mapa.
limiar_do_id <- function(id) {
  m <- regmatches(id, regexec("^mapa([0-9]{2})$", id))[[1]]
  if (length(m) == 2 && as.integer(m[2]) %in% LIMIARES) as.integer(m[2]) else NA_integer_
}

# Uma célula: x = exposição binária do calendário. Devolve c(rr, lo, hi, nd, fam), com NA no RR se a célula não for estimada.
celula_mapa <- function(x, y, b, fora, k_time) {
  ok <- !fora
  nd <- sum(x[ok])
  vazia <- c(rr = NA_real_, lo = NA_real_, hi = NA_real_, nd = nd)
  if (nd < MIN_DIAS_EXPOSTOS || nd > sum(ok) - 30) return(vazia)
  cb <- crossbasis(c(rep(0, LAG), x), lag = LAG, argvar = list(fun = "lin"), arglag = list(fun = "ns", df = 3))
  cb_i <- matrix(as.numeric(cb[-seq_len(LAG), , drop = FALSE]), nrow = length(x), dimnames = list(NULL, colnames(cb)))
  dd <- b; dd$y <- y; dd$y[fora] <- NA
  r <- tryCatch({
    fit <- ajustar_gam(dd, cb_i, NULL, k_time)$fit
    ib <- grep("^cb_i", names(coef(fit)))
    pr <- crosspred(cb, coef = coef(fit)[ib], vcov = vcov(fit)[ib, ib], model.link = "log", at = 1, cen = 0)
    c(rr = unname(pr$allRRfit), lo = unname(pr$allRRlow), hi = unname(pr$allRRhigh), nd = nd)
  }, error = function(e) NULL)
  if (is.null(r) || !all(is.finite(r[c("rr", "lo", "hi")]))) vazia else r
}

# Uma coluna do mapa (um limiar K, todas as horas H): `nh` = horas do dia com índice de calor >= K em cada dia do calendário.
ajustar_mapa_limiar <- function(y, b, nh, fora, k_time, K, horas = HORAS_MAPA) {
  nh[is.na(nh)] <- 0
  m <- sapply(horas, function(h) celula_mapa(as.numeric(nh >= h), y, b, fora, k_time))
  list(tipo = "mapa", limiar = K, h = horas, rr = m["rr", ], lo = m["lo", ], hi = m["hi", ], nd = m["nd", ], n = sum(y[!fora]))
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
