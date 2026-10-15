# Monta o JSON da Figura 1 a partir do contexto de dados e dos ajustes do modelo do João.

arred <- function(x, d) { x <- round(as.numeric(x), d); x[is.nan(x)] <- NA; x }
dec <- function(x) as.integer(round(x * 10))         # esperados diários em décimos de óbito (inteiros ocupam menos no JSON)

# Tabela semanal (semanas epidemiológicas completas, domingo a sábado)
tabela_semanal <- function(cx, sem) {
  g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
  cl <- cx$clima
  nc <- nivel_calor(cl)
  soma <- function(v) as.integer(tapply(v, g, sum))
  nao_na <- function(v) as.integer(tapply(!is.na(v), g, sum))
  mx <- tapply(cl$hi_max, g, function(v) if (all(is.na(v))) NA_real_ else max(v, na.rm = TRUE))
  list(ini = as.character(sem$ini_ok), ano = sem$ano, se = sem$se,
       nb = soma(!is.na(cl$hi_max) & cl$hi_max >= 36),              # dias com índice de calor máx. >= 36 °C
       nn = soma(!is.na(nc) & nc >= 2),                              # dias em NC2 a NC5
       mxh = arred(mx, 1), mt = arred(tapply(cl$t_med, g, mean, na.rm = TRUE), 1),
       cov = as.logical(tapply(cx$covid, g, any)), inc = as.logical(tapply(cx$sem_registro, g, any)),
       nc = as.logical(tapply(cx$nao_consolidado, g, any)) & !as.logical(tapply(cx$sem_registro, g, any)),
       cl = nao_na(cl$hi_max) >= 4)                                  # semana com pelo menos 4 dias de clima
}

montar_figura1 <- function(cx, Y, ajustes, k_time, versao = "1.0") {
  cl <- cx$clima; sem <- semanas(cx$dias); chaves <- names(ajustes[[1]])
  cl_ <- list(hi_max = arred(cl$hi_max, 1), hi_med = arred(cl$hi_med, 2), t_med = arred(cl$t_med, 2),
              h36 = arred(cl$num_hr_36, 0), nc = as.integer(nivel_calor(cl)), ok = as.integer(!is.na(cl$hi_max)))
  m <- list(); S <- list()
  cov_w <- as.logical(tapply(cx$covid, factor(as.character(sem$ini), levels = as.character(sem$ini_ok)), any))
  for (e in names(ajustes)) {
    A <- ajustes[[e]]
    m[[e]] <- list(f = unname(vapply(A, function(r) r$fam, "")), d = unname(arred(vapply(A, function(r) r$disp, 0), 3)),
                   rr = unname(lapply(A, function(r) arred(as.numeric(r$rr), 4))),
                   e = unname(lapply(A, function(r) dec(r$mu_sem_calor))))
    S[[e]] <- lapply(names(A), function(k) { w <- semanal(A[[k]], Y[[k]], sem, cov_w); list(e = arred(w$e, 1), l = arred(w$l, 1), u = arred(w$u, 1), phi = arred(w$phi, 2)) })
    names(S[[e]]) <- names(A)
  }
  So <- lapply(chaves, function(k) as.integer(tapply(Y[[k]], factor(as.character(sem$ini), levels = as.character(sem$ini_ok)), sum)))
  names(So) <- chaves
  rc <- table(cx$d$raca)
  list(
    meta = list(versao = versao, gerado_em = format(Sys.time(), "%Y-%m-%d %H:%M"), pop = cx$pop,
                inicio = as.character(cx$inicio), fim = as.character(cx$fim), n_dias = length(cx$dias), k_tempo = k_time, lag = LAG,
                meses_nc = I(format(cx$meses_nc, "%Y-%m")), dias_sem_registro = sum(cx$sem_registro), dias_nc = sum(cx$nao_consolidado),
                n_obitos = nrow(cx$d), min_obitos = MIN_OBITOS, locais = I(c("Todos os locais", LOCAIS)), faixas = I(c("Todas as idades", FAIXAS)),
                racas = I(RACAS), covid = I(as.character(COVID)),
                exposicoes = lapply(EXPOSICOES, function(e) list(nome = e$nome, ref = I(e$ref), unidade = e$unidade, fun = e$fun, df = e$df))),
    rc = as.list(setNames(as.integer(rc), names(rc))),
    dias = as.character(cx$dias), cl = cl_,
    fl = list(inc = as.integer(cx$sem_registro), nc = as.integer(cx$nao_consolidado), cov = as.integer(cx$covid)),
    sem = tabela_semanal(cx, sem),
    k = I(chaves), o = lapply(chaves, function(k) as.integer(Y[[k]])), m = m, So = So, S = S)
}

escrever_json <- function(x, caminho) {
  txt <- enc2utf8(as.character(jsonlite::toJSON(x, auto_unbox = TRUE, na = "null", digits = NA, null = "null")))
  stopifnot(!grepl("<[0-9a-f]{2}>", txt))                     # rótulo com acento mal codificado apareceria como <c3><a1>
  writeLines(txt, caminho, useBytes = TRUE)
  invisible(file.size(caminho))
}

# Resumo pequeno (metadados e números citados no texto de métodos); o .qmd lê este arquivo em vez do JSON grande.
resumo_figura1 <- function(dados, cx) {
  k0 <- match("Todos os locais|Todas as idades", dados$k)
  list(meta = dados$meta, rc = dados$rc, n_segmentos = length(dados$k),
       n_qp = lapply(dados$m, function(x) sum(x$f == "qp")),
       n_sem_idade = sum(is.na(cx$d$idade_anos)),
       rr_total = lapply(dados$m, function(x) x$rr[[k0]]),
       phi_total = lapply(dados$S, function(x) x[[k0]]$phi))
}

# Bloco HTML bruto com o JSON compactado (zlib + base64); o navegador descompacta com DecompressionStream("deflate").
bloco_dados_html <- function(caminho_json) {
  z <- memCompress(readBin(caminho_json, "raw", file.size(caminho_json)), type = "gzip")
  paste0("```{=html}\n<script id=\"dados-b64\" type=\"text/plain\">", jsonlite::base64_enc(z), "</script>\n```\n")
}
