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
# Ajuste principal (COD_PADRAO): também saem os dias sem dado de clima e os LAG dias seguintes e os meses de registro não consolidado do SIM.
# Um dia sem clima não é um dia sem calor: a exposição desses dias é desconhecida, e a cross-basis dos LAG dias seguintes depende dela.
# Não há termo de dia da semana, como no modelo de referência (o dia da semana foi uma análise de sensibilidade à parte).

suppressPackageStartupMessages({ library(mgcv); library(dlnm) })

LAG <- 10
K_REF <- 12; ANOS_REF <- 12.5
EXPOSICOES <- list(
  horas = list(nome = "Horas por dia com índice de calor ≥ 36 °C", var = "num_hr_36", fun = "ns", df = 1,  ref = c(4, 8),  unidade = "h"),
  haat  = list(nome = "HAAT: graus-hora acima de 36 °C no dia",    var = "auc36",     fun = "ps", df = 15, ref = c(5, 20), unidade = "°C·h"))

# Alternativa flexível pré-definida para as horas por dia: spline natural com 3 gl (nós interiores em 3 e 6 h, que dividem em três partes os dias com calor;
# nós de borda no menor e no maior valor observado). O modelo de referência tem 1 gl na exposição, de modo que o log-RR é uma reta nas horas e
# RR(8 h) = RR(4 h)^2 por construção; esta alternativa não impõe essa forma e serve para verificar se os dados sustentam a reta (ver comparar_flex).
HORAS_NOS <- c(3, 6)
EXPOSICAO_FLEX <- modifyList(EXPOSICOES$horas, list(fun = "ns", df = length(HORAS_NOS) + 1L, knots = HORAS_NOS,
                                                    nome = "Horas por dia com índice de calor ≥ 36 °C, curva flexível"))

# Calendário do modelo: tempo, dia do ano, índice do período COVID e as exposições (dia sem dado de clima = dia sem calor)
base_modelo <- function(cx) {
  n <- length(cx$dias)
  b <- data.frame(dia = cx$dias, time_id = seq_len(n), dia_ano = as.POSIXlt(cx$dias)$yday + 1L)
  b$covid_id <- 0L; b$covid_id[cx$covid] <- seq_len(sum(cx$covid))
  b$covid_ind <- as.numeric(cx$covid)                                       # só para a sensibilidade do termo da COVID-19 (SENS)
  b$dow <- factor(as.POSIXlt(cx$dias)$wday, levels = 0:6)                   # só para a sensibilidade com dia da semana (SENS)
  for (e in EXPOSICOES) { x <- cx$clima[[e$var]]; x[is.na(x)] <- 0; b[[e$var]] <- x }
  b
}

# Dias fora do ajuste (resposta ausente). Sempre saem os dias sem registro no SIM. Opcionalmente, na ordem das caixas do app (1 = retirar do ajuste):
#   covid = os dias do período COVID (sem eles, o termo suave do período some do modelo);
#   nc    = os dias de meses com registro não consolidado;
#   clima = os dias sem dado de clima e os LAG dias seguintes (a cross-basis deles dependeria de exposição ausente). Com clima = FALSE esses dias entram
#           como dias sem calor, que é a especificação anterior do painel e só serve de sensibilidade.
# opc: list(covid, nc, clima) de TRUE/FALSE. Código de três caracteres "covid nc clima": o ajuste principal é COD_PADRAO.
COD_PADRAO <- "011"
opc_de_codigo <- function(cod) { v <- strsplit(cod, "")[[1]] == "1"; list(covid = v[1], nc = v[2], clima = v[3]) }      # "011" -> covid FALSE, nc TRUE, clima TRUE
MOTIVOS_FORA <- c(sem_registro = "sem registro no SIM", clima = "sem dado de clima ou nos 10 dias seguintes", nc = "mês com registro não consolidado", covid = "período da COVID-19")

dias_sem_clima <- function(cx) is.na(cx$clima$hi_max)
dias_clima_afetados <- function(cx, lag = LAG) {            # dias sem clima e os `lag` seguintes
  sem <- which(dias_sem_clima(cx)); n <- length(cx$dias)
  out <- rep(FALSE, n); out[unique(pmin(rep(sem, each = lag + 1) + 0:lag, n))] <- TRUE
  out
}

# Motivo de cada dia fora do ajuste (um só por dia, na ordem de MOTIVOS_FORA); NA = dia no ajuste.
motivo_fora <- function(cx, opc = list(covid = FALSE, nc = FALSE, clima = FALSE), lag = LAG) {
  m <- rep(NA_character_, length(cx$dias))
  marca <- function(v, nome) m[is.na(m) & v] <<- nome
  marca(cx$sem_registro, "sem_registro")
  if (isTRUE(opc$clima)) marca(dias_clima_afetados(cx, lag), "clima")
  if (isTRUE(opc$nc)) marca(cx$nao_consolidado, "nc")
  if (isTRUE(opc$covid)) marca(cx$covid, "covid")
  m
}
fora_ajuste <- function(cx, opc = list(covid = FALSE, nc = FALSE, clima = FALSE), lag = LAG) !is.na(motivo_fora(cx, opc, lag))

# O que o ajuste usa e o que deixa de fora, para mostrar junto do resultado: dias e óbitos no ajuste, primeiro e último dia, e dias e óbitos
# fora do ajuste por motivo (na ordem de MOTIVOS_FORA). y = óbitos por dia do recorte.
resumo_ajuste <- function(cx, y, opc) {
  m <- motivo_fora(cx, opc); dentro <- is.na(m)
  list(nd = sum(dentro), no = sum(y[dentro]), ini = as.character(cx$dias[dentro][1]), fim = as.character(cx$dias[dentro][sum(dentro)]),
       xd = I(vapply(names(MOTIVOS_FORA), function(k) sum(m %in% k), 1L, USE.NAMES = FALSE)),
       xo = I(vapply(names(MOTIVOS_FORA), function(k) as.integer(sum(y[m %in% k])), 1L, USE.NAMES = FALSE)))
}

k_tempo <- function(n_dias) max(round(K_REF * n_dias / (ANOS_REF * 365.25)), 6)

# Cross-basis de uma exposição. Os 10 dias anteriores ao início entram como dia sem calor, para a cross-basis valer desde o primeiro dia.
# Guarda também a linha da cross-basis para exposição zero em todas as defasagens (c0), usada no contrafactual.
cross_exposicao <- function(b, e, lag = LAG) {
  x <- b[[e$var]]
  argvar <- if (!is.null(e$knots)) list(fun = e$fun, knots = e$knots) else list(fun = e$fun, df = e$df)
  cb <- crossbasis(c(rep(0, lag), x), lag = lag, argvar = argvar, arglag = list(fun = "ns", df = 3))
  m <- matrix(as.numeric(cb[-seq_len(lag), , drop = FALSE]), nrow = length(x), dimnames = list(NULL, colnames(cb)))
  nz <- cumsum(x != 0); janela_com_calor <- nz - c(rep(0, lag + 1), head(nz, -(lag + 1)))
  i0 <- which(seq_along(x) > lag & janela_com_calor == 0)[1]
  stopifnot(!is.na(i0))
  list(obj = cb, m = m, c0 = m[i0, ], pen = if (e$fun == "ps") cbPen(cb) else NULL, e = e, lag = lag)
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
# `esp` = especificação alternativa, só para as análises de sensibilidade (ver SENS); vazia = modelo de referência:
#   esp$dow = TRUE        acrescenta o dia da semana (fator de 7 níveis);
#   esp$covid = "cc"      (padrão) s(covid_id, k = 8, bs = "cc"): spline cíclico no índice do período; fora do período o índice é 0 e o spline cíclico
#                         obriga o valor do último dia a voltar ao do índice 0;
#                         "cr"  spline cúbico não cíclico no índice, só dentro do período, mais o indicador do período;
#                         "obs" spline no log da média móvel de 7 dias dos óbitos diários de COVID-19 do recorte (coluna covid_obs);
#                         "sem" nenhum termo para a pandemia (o período fica no ajuste).
ajustar_gam <- function(dd, cb_i, pen, k_time, esp = list()) {
  covid_modo <- if (is.null(esp$covid)) "cc" else esp$covid
  termos <- c("cb_i", sprintf("s(time_id, k = %d, bs = \"tp\")", as.integer(k_time)), "s(dia_ano, k = 6, bs = \"cc\")")
  if (covid_modo == "obs") termos <- c(termos, "s(covid_obs, k = 5, bs = \"cr\")")
  else if (covid_modo != "sem" && any(dd$covid_id[!is.na(dd$y)] > 0))        # sem dias de COVID no ajuste (retirados, ou dados de teste): sem o termo
    termos <- c(termos, if (covid_modo == "cr") c("covid_ind", "s(covid_id, k = 8, bs = \"cr\", by = covid_ind)") else "s(covid_id, k = 8, bs = \"cc\")")
  if (isTRUE(esp$dow)) termos <- c(termos, "dow")
  fm <- stats::as.formula(paste("y ~", paste(termos, collapse = " + ")), env = environment())
  fam <- "nb"
  fit <- tryCatch(suppressWarnings(gam(fm, data = dd, family = nb(), paraPen = pen, method = "REML")), error = function(e) NULL)
  if (is.null(fit) || !isTRUE(fit$converged)) {
    fit <- suppressWarnings(gam(fm, data = dd, family = quasipoisson(), paraPen = pen, method = "REML")); fam <- "qp"
  }
  list(fit = fit, fam = fam)
}

# Ajusta um segmento. y = óbitos por dia (calendário completo); fora = dias fora do ajuste (sem registro no SIM).
# Devolve a família usada, o RR acumulado nas exposições de referência e os vetores diários (NA fora do ajuste).
ajustar_segmento <- function(y, b, cbi, fora, k_time, esp = list(), curvas = TRUE, diag = "nao", manter_fit = FALSE) {
  dd <- b; dd$y <- y; dd$y[fora] <- NA
  cb_i <- cbi$m
  g <- ajustar_gam(dd, cb_i, if (is.null(cbi$pen)) NULL else list(cb_i = cbi$pen), k_time, esp)
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
  out <- list(fam = fam, disp = disp, n = sum(dd$y[ok]),
       rr = rbind(rr = pr$allRRfit, lo = pr$allRRlow, hi = pr$allRRhigh), se = as.numeric(pr$allse),     # se = erro-padrão do log do RR em cada nível de referência
       curvas = if (curvas) curvas_modelo(cbi, beta, V, ceiling(quantile(b[[cbi$e$var]][b[[cbi$e$var]] > 0], 0.99))),
       mu_ajustado = exp(eta), mu_sem_calor = exp(eta - efeito), efeito = efeito,
       dev_expl = summary(fit)$dev.expl,
       cb = list(k = length(ib), edf = round(sum(fit$edf[ib]), 2)))       # colunas da cross-basis e graus de liberdade efetivos que o ajuste lhe deu
  if (manter_fit) { out$fit <- fit; out$ib <- ib; out$beta <- beta; out$V <- V }
  if (diag != "nao") out$diag <- diagnosticar_fit(fit, ok, ib, completo = identical(diag, "completo"))
  out
}

# ---------------------------------------------------------------- diagnósticos do modelo ajustado
ACF_MAX <- 35                  # defasagens da ACF dos resíduos de Pearson (dias)
LB_LAGS <- 14                  # defasagens do teste de Ljung-Box (duas semanas)
# fit = gam ajustado; ok = dias do calendário usados no ajuste; ib = posição dos coeficientes da cross-basis.
# Resíduos de Pearson na escala diária; a ACF ignora os dias fora do ajuste (pares com dia ausente não entram) e o limite aproximado de 95% é 1,96/raiz(n).
# Ljung-Box com LB_LAGS defasagens, sem desconto dos graus de liberdade do modelo (por isso o valor de p é um indicador, não um teste exato).
# completo = TRUE acrescenta k.check do mgcv (índice k, dimensão da base e graus de liberdade efetivos de cada termo suave), com semente fixa.
diagnosticar_fit <- function(fit, ok, ib, completo = FALSE) {
  res <- as.numeric(residuals(fit, type = "pearson")); nobs <- sum(ok)
  r <- rep(NA_real_, length(ok)); r[ok] <- res
  rho <- as.numeric(stats::acf(r, lag.max = ACF_MAX, na.action = stats::na.pass, plot = FALSE)$acf)[-1]
  lim <- 1.96 / sqrt(nobs); k <- seq_len(LB_LAGS)
  Q <- nobs * (nobs + 2) * sum(rho[k]^2 / (nobs - k))
  gl_res <- nobs - sum(fit$edf)
  oi <- fit$outer.info
  d <- list(n = nobs, acf = round(rho, 4), lim = round(lim, 4), n_acf = sum(abs(rho) > lim), rho1 = round(rho[1], 3), rho7 = round(rho[7], 3),
            lb = list(q = round(Q, 2), gl = LB_LAGS, p = stats::pchisq(Q, LB_LAGS, lower.tail = FALSE)),
            chi2_gl = round(sum(res^2) / gl_res, 3), gl_res = round(gl_res, 1), dev_expl = round(summary(fit)$dev.expl, 4),
            cb = list(k = length(ib), edf = round(sum(fit$edf[ib]), 2)), gl_total = round(sum(fit$edf), 1),
            conv = list(ok = isTRUE(fit$converged), msg = if (is.list(oi) && !is.null(oi$conv)) as.character(oi$conv)[1] else NA_character_,
                        iter = if (is.list(oi) && !is.null(oi$iter)) as.integer(oi$iter) else NA_integer_,
                        grad = if (is.list(oi) && !is.null(oi$grad)) signif(max(abs(oi$grad)), 3) else NA_real_, pirls = as.integer(fit$iter)))
  if (completo) {
    antes <- if (exists(".Random.seed", envir = globalenv(), inherits = FALSE)) get(".Random.seed", envir = globalenv()) else NULL
    set.seed(20260101)
    kc <- tryCatch(suppressWarnings(mgcv::k.check(fit, n.rep = 200)), error = function(e) NULL)
    if (!is.null(antes)) assign(".Random.seed", antes, envir = globalenv())
    cc <- tryCatch({                       # implementação do spline cíclico da pandemia: valor do termo fora do período, no último dia e no pico
      tt <- predict(fit, type = "terms"); col <- "s(covid_id)"; ci <- fit$model$covid_id
      if (col %in% colnames(tt) && any(ci > 0)) list(fora = round(mean(tt[ci == 0, col]), 4), ultimo = round(mean(tt[ci == max(ci), col]), 4),
                                                     primeiro = round(mean(tt[ci == 1, col]), 4), pico = round(tt[which.max(abs(tt[, col])), col], 4)) else NULL
    }, error = function(e) NULL)
    if (!is.null(cc)) d$covid_cc <- cc
    st <- tryCatch(summary(fit)$s.table, error = function(e) NULL)
    if (!is.null(kc)) d$suaves <- lapply(rownames(kc), function(nm) list(termo = nm, k = unname(kc[nm, "k'"]), edf = round(unname(kc[nm, "edf"]), 2),
                                                                        kindex = round(unname(kc[nm, "k-index"]), 3), p = unname(kc[nm, "p-value"]),
                                                                        p_termo = if (!is.null(st) && nm %in% rownames(st)) unname(st[nm, ncol(st)]) else NA_real_))
  }
  d
}

# ---------------------------------------------------------------- forma da relação exposição-resposta (horas por dia)
# RR de `b` contra `a` (acumulado em 0 a LAG dias, exposição mantida em todos os dias) e IC 95%, a partir dos coeficientes da cross-basis.
rr_contra <- function(cbi, beta, V, a, b) {
  pr <- crosspred(cbi$obj, coef = beta, vcov = V, model.link = "log", at = c(a, b), cen = a)
  i <- which(abs(pr$predvar - b) < 1e-8)
  c(rr = unname(pr$allRRfit[i]), lo = unname(pr$allRRlow[i]), hi = unname(pr$allRRhigh[i]))
}

# Compara o ajuste de referência (reta imposta, 1 gl) com a curva flexível pré-definida (EXPOSICAO_FLEX) no mesmo recorte, causa e retiradas.
# Devolve, para cada um, o RR nos níveis de referência, o RR de 8 h contra 4 h, a curva com IC 95% e os graus de liberdade; e a comparação dos dois:
# razão de desvios aproximada (anova.gam; a reta está contida na curva flexível), diferença de AIC e a razão log RR(8 h) / log RR(4 h) (2 na reta).
comparar_flex <- function(y, b, cbl, cbf, fora, k_time) {
  rnd <- function(x, d) { x <- round(as.numeric(x), d); x }
  rl <- ajustar_segmento(y, b, cbl, fora, k_time, curvas = TRUE, manter_fit = TRUE)
  rf <- ajustar_segmento(y, b, cbf, fora, k_time, curvas = TRUE, manter_fit = TRUE)
  ref <- cbl$e$ref
  um <- function(r, cbi) {
    cv <- r$curvas
    list(rr = rnd(r$rr["rr", ], 4), lo = rnd(r$rr["lo", ], 4), hi = rnd(r$rr["hi", ], 4),
         r84 = rnd(rr_contra(cbi, r$beta, r$V, ref[1], ref[2]), 4),
         k = r$cb$k, edf = r$cb$edf, aic = round(AIC(r$fit), 1), f = r$fam,
         cv = list(x = rnd(cv$x, 3), rr = rnd(cv$rr, 4), lo = rnd(cv$lo, 4), hi = rnd(cv$hi, 4)))
  }
  an <- tryCatch(suppressWarnings(stats::anova(rl$fit, rf$fit, test = "Chisq")), error = function(e) NULL)
  comp <- list(d_aic = round(AIC(rf$fit) - AIC(rl$fit), 1), razao = rnd(log(rf$rr["rr", 2]) / log(rf$rr["rr", 1]), 3))
  if (!is.null(an) && nrow(an) == 2 && "Pr(>Chi)" %in% colnames(an)) {
    comp$gl <- round(an$Df[2], 2); comp$desvio <- round(an$Deviance[2], 2); comp$p <- unname(an[2, "Pr(>Chi)"])
  }
  list(lin = um(rl, cbl), flex = um(rf, cbf), comp = comp)
}

# ---------------------------------------------------------------- suporte dos contrastes acumulados (aba Exposição-resposta)
# O RR acumulado de 0 a LAG dias descreve a exposição r mantida em todos os LAG+1 dias, mas a série pode quase não ter essa sequência. Para cada nível de
# referência r, conta quantas vezes a série tem exposição x >= r em todos os d dias seguidos até o dia do óbito (para as durações d de DURACOES), em quantos
# eventos independentes isso ocorre, a duração observada das sequências de dias expostos e a distribuição por ano.
#   dia exposto           x >= r (dia sem dado de clima conta como não exposto: a exposição é desconhecida)
#   sequência             dias expostos seguidos
#   janela de d dias      dia t do ajuste em que os d dias t-d+1, ..., t são todos expostos (a sequência que termina em t tem pelo menos d dias)
#   evento independente   conjunto de dias expostos em que dois dias expostos consecutivos distam no máximo `lag` dias: eventos distintos têm pelo menos `lag` dias
#                         sem exposição entre eles, de modo que as janelas de defasagem de eventos diferentes não se tocam
#   janela de média       dia t do ajuste em que a média de x nos lag+1 dias t-lag, ..., t é pelo menos r (exposição total comparável, com dias acima e abaixo de r)
# x = exposição diária do calendário (dia sem clima = 0), fora = dias fora do ajuste (como desfecho), ref = níveis de referência.
DURACOES <- c(1, 2, 4, 8, 11)
CLASSES_DURACAO <- c("1 dia", "2 a 3 dias", "4 a 7 dias", "8 a 10 dias", "11 dias ou mais")
suporte_exposicao <- function(x, dias, fora, ref, lag = LAG, dur = DURACOES) {
  n <- length(x); ano <- as.integer(format(dias, "%Y")); anos <- sort(unique(ano[!fora]))
  por_ano <- function(v) { r <- as.integer(tapply(v, factor(ano, levels = anos), sum)); r[is.na(r)] <- 0L; r }
  cs <- c(0, cumsum(x)); tt <- seq_len(n); soma_lag <- ifelse(tt >= lag + 1, cs[tt + 1] - cs[pmax(tt - lag, 1)], NA_real_)      # soma de x nos lag+1 dias terminados em t
  niveis <- lapply(ref, function(r) {
    e <- x >= r
    rl <- rle(e); fim <- cumsum(rl$lengths); ini <- fim - rl$lengths + 1
    L <- integer(n)                                                   # dias expostos seguidos que terminam em t
    for (k in which(rl$values)) L[ini[k]:fim[k]] <- seq_len(rl$lengths[k])
    ie <- which(e); grp <- cumsum(c(TRUE, diff(ie) > lag))            # evento independente de cada dia exposto
    janelas <- vapply(dur, function(d) as.integer(sum(L >= d & !fora)), 1L)
    eventos <- vapply(dur, function(d) length(unique(grp[L[ie] >= d & !fora[ie]])), 1L)
    seqs <- which(rl$values); com_dia_no_ajuste <- vapply(seqs, function(k) any(!fora[ini[k]:fim[k]]), TRUE)
    classe <- cut(rl$lengths[seqs][com_dia_no_ajuste], c(0, 1, 3, 7, 10, Inf), labels = CLASSES_DURACAO)
    seq4 <- por_ano(L == 4 & !fora)                                   # a sequência entra no ano em que completa o 4º dia exposto, com esse dia no ajuste
    list(ref = r, dias = sum(e & !fora), janelas = I(janelas), eventos = I(eventos), janelas_media = sum(soma_lag >= r * (lag + 1) - 1e-9 & !fora, na.rm = TRUE),
         duracao = list(classe = I(CLASSES_DURACAO), n = I(as.integer(table(classe)))),
         anual = list(ano = I(anos), dias = I(por_ano(e & !fora)), seq4 = I(seq4), jan11 = I(por_ano(L >= lag + 1 & !fora))))
  })
  list(ref = I(ref), dur = I(dur), lag = lag, nd = sum(!fora), niveis = niveis)
}

# ---------------------------------------------------------------- análises de sensibilidade (aba Diagnósticos e sensibilidades)
# Cada uma refaz o ajuste do recorte com uma só mudança em relação ao ajuste principal pedido (causa, retiradas e medida de calor iguais).
#   esp   especificação alternativa do GAM (ver ajustar_gam);  kmult  fator sobre o número de nós do spline do tempo;  lag  defasagem máxima (dias);
#   opc   o que muda nas retiradas do ajuste (ver fora_ajuste): FALSE/TRUE sobre o código pedido.
SENS <- list(
  dow       = list(rot = "Dia da semana como termo do modelo", grupo = "Termo temporal", esp = list(dow = TRUE)),
  k_meta    = list(rot = "Spline do tempo com metade dos nós", grupo = "Termo temporal", kmult = 0.5),
  k_dobro   = list(rot = "Spline do tempo com o dobro dos nós", grupo = "Termo temporal", kmult = 2),
  lag7      = list(rot = "Defasagem máxima de 7 dias", grupo = "Defasagem", lag = 7),
  lag14     = list(rot = "Defasagem máxima de 14 dias", grupo = "Defasagem", lag = 14),
  covret    = list(rot = "Período da COVID-19 retirado do ajuste", grupo = "Período da COVID-19", opc = list(covid = TRUE)),
  covsem    = list(rot = "Período da COVID-19 mantido, sem termo próprio", grupo = "Período da COVID-19", esp = list(covid = "sem")),
  covcr     = list(rot = "Termo da COVID-19 não cíclico (spline cúbico, k = 8) com indicador do período", grupo = "Período da COVID-19", esp = list(covid = "cr")),
  covobs    = list(rot = "Termo da COVID-19 pelos óbitos diários de COVID-19 (média móvel de 7 dias, k = 5)", grupo = "Período da COVID-19", esp = list(covid = "obs")),
  ncmant    = list(rot = "Meses de registro não consolidado mantidos no ajuste", grupo = "Amostra", opc = list(nc = FALSE)),
  climazero = list(rot = "Dias sem dado de clima contados como dias sem calor", grupo = "Amostra", opc = list(clima = FALSE)),
  anterior  = list(rot = "Especificação anterior do painel: meses não consolidados mantidos e dias sem clima contados como dias sem calor", grupo = "Amostra", opc = list(nc = FALSE, clima = FALSE)))

# Dias de calor (pelo menos LIM_DIA_CALOR h com índice de calor >= 36 °C, como no protocolo) dentro do ajuste e eventos (sequências de dias seguidos de calor).
LIM_DIA_CALOR <- 4
contagem_calor <- function(cx, fora) {
  x <- cx$clima$num_hr_36; x[is.na(x)] <- 0
  d <- x >= LIM_DIA_CALOR & !fora; r <- rle(d)
  list(dias = sum(d), eventos = sum(r$values))
}

# Resumo do diagnóstico residual de um ajuste, para a coluna de cada análise de sensibilidade.
resumo_residual <- function(d) list(lb_p = d$lb$p, n_acf = d$n_acf, rho1 = d$rho1, chi2_gl = d$chi2_gl, edf_cb = d$cb$edf)


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
