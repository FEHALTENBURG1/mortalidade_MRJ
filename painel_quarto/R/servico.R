# Serviço de ajuste sob demanda do painel Shiny.
#
# O app não ajusta nada ao abrir: lê o contexto já pronto do cache de dados (R/fontes_remotas.R) e, quando o usuário escolhe um recorte, uma medida
# de calor, uma causa de óbito e o que retirar do ajuste, ajusta só aquele modelo de referência (R/modelo_joao.R) e guarda o resultado em disco. O mesmo
# pedido, feito de novo por qualquer usuário, sai do disco. As mesmas funções rodam no processo principal (testes) e nos trabalhadores do pacote future (app).
#
# Pedido = população + causa + retiradas + medida de calor + recorte.
#   causa:     uma das CAUSAS (R/funcoes.R): naturais, todas_sem_covid, todas, externas.
#   retiradas: código de 3 caracteres 0/1, na ordem COVID, meses não consolidados, dias sem clima (ver fora_ajuste() em R/modelo_joao.R).
#              "000" é o modelo padrão (só os dias sem registro no SIM saem do ajuste).
# Cache de ajustes: <cache>/ajustes/<chave>/<pop>_<medida>_<hash de causa, retiradas e recorte>.rds. A chave é a versão dos dados; versão nova,
# pasta nova (atualizar_cache() apaga as pastas das versões antigas). Um ajuste é gravado em arquivo temporário e renomeado, como o contexto.

.servico <- new.env()                       # estado do processo: modelo preparado de cada população

VERSAO_AJUSTE <- 2L                         # muda quando o conteúdo do payload muda (ajustes gravados com outra versão são refeitos)

CODIGOS_OPC <- c("000", "001", "010", "011", "100", "101", "110", "111")
opc_de_codigo <- function(cod) { v <- strsplit(cod, "")[[1]] == "1"; list(covid = v[1], nc = v[2], clima = v[3]) }
codigo_valido <- function(cod) is.character(cod) && length(cod) == 1 && !is.na(cod) && cod %in% CODIGOS_OPC

# ---------------------------------------------------------------- preparo do modelo a partir do contexto
preparar_modelo <- function(cx) {
  sem <- semanas(cx$dias)
  g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
  list(cx = cx, Yc = new.env(), b = base_modelo(cx), kt = k_tempo(length(cx$dias)), sem = sem,
       cov_w = as.logical(tapply(cx$covid, g, any)), cbi = new.env(), Rc = new.env())
}

# Séries diárias por segmento de uma causa (calculadas na primeira vez que a causa é pedida).
y_causa <- function(P, causa) {
  if (is.null(P$Yc[[causa]])) assign(causa, series_segmentos(obitos_causa(P$cx, causa), P$cx$dias), envir = P$Yc)
  P$Yc[[causa]]
}

# Recortes com pelo menos MIN_OBITOS óbitos no ajuste, para cada causa e cada código de retiradas: list(causa = list(codigo = c(chaves)))
elegibilidade <- function(P) {
  fora <- lapply(CODIGOS_OPC, function(cod) fora_ajuste(P$cx, opc_de_codigo(cod))); names(fora) <- CODIGOS_OPC
  sapply(names(CAUSAS), function(causa) {
    Y <- y_causa(P, causa); Ym <- do.call(cbind, Y)
    sapply(CODIGOS_OPC, function(cod) names(Y)[colSums(Ym[!fora[[cod]], , drop = FALSE]) >= MIN_OBITOS], simplify = FALSE)
  }, simplify = FALSE)
}

# Modelo preparado da população `pop`, lido do cache de dados e guardado na memória do processo. Se `chave` for dada e o cache já estiver em outra
# versão, devolve NULL (o pedido é de uma versão antiga). Se o cache mudou desde a última leitura, recarrega.
obter_P <- function(pasta, pop, chave = NULL) {
  m <- meta_cache(pasta, pop)
  if (is.null(m)) return(NULL)
  if (!is.null(chave) && !identical(m$chave, chave)) return(NULL)
  atual <- .servico[[pop]]
  if (!is.null(atual) && identical(atual$chave, m$chave)) return(atual)
  x <- ler_contexto(pasta, pop)
  if (is.null(x)) return(NULL)
  P <- preparar_modelo(x$cx); P$chave <- x$meta$chave; P$meta <- x$meta
  assign(pop, P, envir = .servico)
  P
}

cbi_de <- function(P, expo) {
  if (is.null(P$cbi[[expo]])) assign(expo, cross_exposicao(P$b, EXPOSICOES[[expo]]), envir = P$cbi)
  P$cbi[[expo]]
}

# Pedido válido: uma das EXPOSICOES (modelo de referência), "mapa<K>" (coluna do mapa de horas por limiar, K em LIMIARES) ou um pedido da aba de causas
# específicas ("cidlista", "cid_<CID>_<medida>", "cidsem_<CID>_<medida>"; ver cid_do_id()).
expo_valida <- function(expo) is.character(expo) && length(expo) == 1 && !is.na(expo) &&
  (expo %in% names(EXPOSICOES) || !is.na(limiar_do_id(expo)) || !is.null(cid_do_id(expo)))

# Ajusta um recorte (chave "local|faixa" ou "local|Todas as idades|raça") para uma medida de calor, uma causa e um conjunto de retiradas;
# devolve o payload da figura (ou, para "mapa<K>", o payload da coluna K do mapa).
ajustar_recorte <- function(P, key, expo, causa = "naturais", cod = "000") {
  stopifnot(expo_valida(expo), codigo_valido(cod))
  y <- y_do_pedido(P, causa, key, expo)
  stopifnot(!is.null(y))
  fora <- fora_ajuste(P$cx, opc_de_codigo(cod))
  K <- limiar_do_id(expo)
  if (!is.na(K)) return(ajustar_mapa_limiar(y, P$b, P$cx$clima[[paste0("num_hr_", K)]], fora, P$kt, K))
  pc <- cid_do_id(expo)
  if (!is.null(pc)) return(ajustar_pedido_cid(P, pc, key, causa, cod, y, fora))
  r <- ajustar_segmento(y, P$b, cbi_de(P, expo), fora, P$kt)
  payload_segmento(r, y, P$sem, P$cov_w, curvas = TRUE)
}

# Dados-base da figura (calendário, clima, sinalizações) mais o que o navegador precisa saber no modo sob demanda: causas, recortes elegíveis
# para cada combinação de causa e retiradas e a distribuição de raça/cor de cada causa. `elig` = elegibilidade(P), lida do disco quando existe.
base_sob_demanda <- function(P, elig = elegibilidade(P), cid_nomes = NULL) {
  b <- base_figura1(P$cx, P$kt)
  b$meta$elegiveis <- lapply(elig, function(porcod) lapply(porcod, I))
  b$meta$causas <- as.list(CAUSAS)
  b$meta$sob_demanda <- TRUE
  b$meta$cid_min <- CID_MIN
  if (!is.null(cid_nomes)) b$meta$cid_nomes <- as.list(cid_nomes)
  b$meta$dados <- list(chave = P$meta$chave, sim_atualizado = P$meta$sim_atualizado, clima_atualizado = P$meta$clima_atualizado, repo_sim = P$meta$repo_sim,
                       gerado_em = P$meta$gerado_em)
  b$rcs <- sapply(names(CAUSAS), function(causa) { rc <- table(obitos_causa(P$cx, causa)$raca); as.list(setNames(as.integer(rc), names(rc))) }, simplify = FALSE)
  b
}

# A elegibilidade custa alguns segundos (séries de quatro causas); fica no disco, por versão dos dados.
obter_elegibilidade <- function(pasta, pop, P) {
  f <- file.path(pasta, sprintf("elegibilidade_%s_%s.rds", pop, P$chave))
  x <- if (file.exists(f)) tryCatch(readRDS(f), error = function(e) NULL) else NULL
  if (!is.null(x)) return(x)
  x <- elegibilidade(P)
  tmp <- paste0(f, ".", Sys.getpid(), ".parte"); saveRDS(x, tmp); file.rename(tmp, f)
  unlink(setdiff(Sys.glob(file.path(pasta, sprintf("elegibilidade_%s_*.rds", pop))), f))
  x
}

# ---------------------------------------------------------------- causas específicas (CID-10)
# A aba de causas específicas avalia, para um recorte (local, faixa etária ou raça/cor), cada causa básica de 3 caracteres com pelo menos CID_MIN óbitos no
# ajuste. Cada causa é um modelo de referência próprio. Os pedidos usam o campo "medida de calor" do protocolo com identificadores próprios:
#   cidlista               causas avaliadas no recorte e o número de óbitos de cada uma (sem ajuste de modelo)
#   cid_<CID>_<medida>     RR nos dois níveis de referência da medida (horas ou haat), com IC 95% e valor de p
#   cidsem_<CID>_<medida>  o mesmo ajuste com a série semanal observada e esperada da causa (a Figura 1 de uma causa)
CID_MIN <- 1500

cid_do_id <- function(id) {
  if (!is.character(id) || length(id) != 1 || is.na(id)) return(NULL)
  if (identical(id, "cidlista")) return(list(tipo = "cidlista", cid = NA_character_, medida = NA_character_))
  m <- regmatches(id, regexec("^(cid|cidsem)_([A-Z][0-9]{2})_(horas|haat)$", id))[[1]]
  if (length(m) == 4) list(tipo = m[2], cid = m[3], medida = m[4]) else NULL
}

ler_cid_nomes <- function(raiz) jsonlite::fromJSON(file.path(raiz, "dados_auxiliares", "cid_nomes.json"))

# Óbitos de uma causa (ver CAUSAS) com a causa básica de 3 caracteres, a partir de um contexto enxuto.
obitos_causa_cid <- function(cx, causa) {
  stopifnot(causa %in% names(CAUSAS))
  cols <- c(COLUNAS_SERIE, "cid")
  nat <- cx$d[, cols]
  if (causa == "naturais") return(nat)
  if (is.null(cx$d_extra$cid)) stop("recorte_invalido: o cache do servidor não traz a causa básica dos óbitos não naturais; atualize-o com shiny/atualizar_cache.R --forcar", call. = FALSE)
  ex <- cx$d_extra
  switch(causa,
         externas = ex[!ex$covid, cols],
         todas_sem_covid = rbind(nat, ex[!ex$covid, cols]),
         todas = rbind(nat, ex[, cols]))
}

# Óbitos do recorte `key` na causa `causa` (dia como posição no calendário e causa básica). Fica na memória do processo; só os últimos recortes são mantidos.
obitos_recorte_cid <- function(P, causa, key) {
  id <- paste(causa, key, sep = "\r")
  if (!is.null(P$Rc[[id]])) return(P$Rc[[id]])
  d <- obitos_causa_cid(P$cx, causa)
  p <- strsplit(key, "|", fixed = TRUE)[[1]]
  sel <- rep(TRUE, nrow(d))
  if (p[1] != "Todos os locais") sel <- sel & d$local == p[1]
  if (p[2] != "Todas as idades") sel <- sel & d$faixa %in% p[2]
  if (length(p) >= 3) sel <- sel & (if (p[3] == "PPI") d$raca %in% PPI else d$raca == p[3])
  r <- list(dia = match(as.integer(d$dia[sel]), as.integer(P$cx$dias)), cid = d$cid[sel], n_dias = length(P$cx$dias))
  velhos <- setdiff(ls(P$Rc), id)
  if (length(velhos) >= 4) rm(list = velhos, envir = P$Rc)
  assign(id, r, envir = P$Rc)
  r
}

# Série diária de óbitos de uma causa básica no recorte.
y_cid <- function(P, causa, key, cid) {
  r <- obitos_recorte_cid(P, causa, key)
  tabulate(r$dia[r$cid == cid], nbins = r$n_dias)
}

# Série diária do pedido (segmento da Figura 1, coluna do mapa ou causa específica); NULL se o recorte não existe.
y_do_pedido <- function(P, causa, key, expo) {
  y <- y_causa(P, causa)[[key]]
  pc <- cid_do_id(expo)
  if (is.null(y) || is.null(pc) || pc$tipo == "cidlista") return(y)
  y_cid(P, causa, key, pc$cid)
}

# Causas avaliadas no recorte: as com pelo menos CID_MIN óbitos nos dias do ajuste, da maior para a menor.
lista_cid <- function(P, causa, cod, key) {
  r <- obitos_recorte_cid(P, causa, key)
  fora <- fora_ajuste(P$cx, opc_de_codigo(cod))
  ok <- !is.na(r$dia); ok[ok] <- !fora[r$dia[ok]]
  tb <- table(r$cid[ok]); tb <- sort(tb[tb >= CID_MIN], decreasing = TRUE)
  list(tipo = "cidlista", n_dias_ajuste = sum(!fora), cid = I(names(tb)), n = I(as.integer(tb)))
}

# Ajuste de uma causa. Payload leve (cid_*): RR nos dois níveis de referência, IC 95% e valor de p (aproximação normal do log do RR).
# Com série semanal (cidsem_*): o payload completo de um recorte da Figura 1, para a causa.
ajustar_pedido_cid <- function(P, pc, key, causa, cod, y, fora) {
  if (pc$tipo == "cidlista") return(lista_cid(P, causa, cod, key))
  r <- ajustar_segmento(y, P$b, cbi_de(P, pc$medida), fora, P$kt)
  if (pc$tipo == "cidsem") return(c(list(tipo = "cidsem", cid = pc$cid, medida = pc$medida), payload_segmento(r, y, P$sem, P$cov_w, curvas = FALSE)))
  list(tipo = "cid", cid = pc$cid, medida = pc$medida, n = sum(y[!fora]), ref = I(EXPOSICOES[[pc$medida]]$ref),
       rr = arred(r$rr["rr", ], 4), lo = arred(r$rr["lo", ], 4), hi = arred(r$rr["hi", ], 4),
       p = unname(signif(2 * pnorm(-abs(log(r$rr["rr", ]) / r$se)), 4)), f = r$fam, d = arred(r$disp, 3))
}

# ---------------------------------------------------------------- cache de ajustes em disco
arquivo_ajuste <- function(pasta, chave, pop, expo, key, causa = "naturais", cod = "000")
  file.path(pasta, "ajustes", chave, sprintf("%s_%s_%s.rds", pop, expo, substr(md5_texto(enc2utf8(paste(causa, cod, key, sep = "\r"))), 1, 12)))

ler_ajuste <- function(pasta, chave, pop, expo, key, causa = "naturais", cod = "000") {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key, causa, cod)
  if (!file.exists(f)) return(NULL)
  x <- tryCatch(readRDS(f), error = function(e) NULL)
  if (is.null(x) || !identical(x$versao, VERSAO_AJUSTE) || !identical(x$key, key) || !identical(x$expo, expo) || !identical(x$causa, causa) || !identical(x$cod, cod)) return(NULL)   # corrompido, de versão antiga ou colisão de hash
  x$payload
}

gravar_ajuste <- function(payload, pasta, chave, pop, expo, key, causa = "naturais", cod = "000") {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key, causa, cod)
  dir.create(dirname(f), showWarnings = FALSE, recursive = TRUE)
  tmp <- paste0(f, ".", Sys.getpid(), ".parte")
  saveRDS(list(versao = VERSAO_AJUSTE, key = key, expo = expo, causa = causa, cod = cod, pop = pop, chave = chave, payload = payload), tmp)
  file.rename(tmp, f)
  invisible(f)
}

# Apaga os ajustes de versões antigas dos dados (tudo em ajustes/ que não seja a pasta da versão atual).
limpar_ajustes_antigos <- function(pasta, chave_atual) {
  base <- file.path(pasta, "ajustes")
  if (!dir.exists(base)) return(invisible(0))
  pastas <- list.dirs(base, recursive = FALSE, full.names = TRUE)
  velhas <- pastas[basename(pastas) != chave_atual]
  unlink(velhas, recursive = TRUE)
  invisible(length(velhas))
}

# ---------------------------------------------------------------- execução de um pedido (processo principal ou trabalhador)
# Devolve list(payload, do_cache, segundos). Erros começam com um código: "dados_mudaram:" (o cache saiu da versão do pedido) ou "recorte_invalido:".
executar_ajuste <- function(pasta, pop, chave, key, expo, causa = "naturais", cod = "000") {
  if (!causa %in% names(CAUSAS) || !codigo_valido(cod)) stop("recorte_invalido: causa do óbito ou retiradas do ajuste não reconhecidas", call. = FALSE)
  x <- ler_ajuste(pasta, chave, pop, expo, key, causa, cod)
  if (!is.null(x)) return(list(payload = x, do_cache = TRUE, segundos = 0))
  P <- obter_P(pasta, pop, chave)
  if (is.null(P)) stop("dados_mudaram: o cache de dados mudou de versão; recarregue a página", call. = FALSE)
  y <- if (expo_valida(expo)) y_do_pedido(P, causa, key, expo) else NULL
  if (is.null(y)) stop("recorte_invalido: recorte ou medida de calor não reconhecidos", call. = FALSE)
  minimo <- if (!is.null(cid_do_id(expo)) && cid_do_id(expo)$tipo != "cidlista") CID_MIN else MIN_OBITOS
  if (sum(y[!fora_ajuste(P$cx, opc_de_codigo(cod))]) < minimo) stop("recorte_invalido: óbitos insuficientes no ajuste", call. = FALSE)
  t0 <- Sys.time()
  x <- ajustar_recorte(P, key, expo, causa, cod)
  gravar_ajuste(x, pasta, chave, pop, expo, key, causa, cod)
  list(payload = x, do_cache = FALSE, segundos = as.numeric(difftime(Sys.time(), t0, units = "secs")))
}

# ---------------------------------------------------------------- pedidos assíncronos (app): trabalhadores do future, sem repetir o mesmo pedido
.pendentes <- new.env()

# Devolve uma promessa com o resultado de executar_ajuste(). Pedidos iguais em andamento compartilham a mesma promessa.
# Pede ao future um trabalhador que carrega o código de `raiz` na primeira vez e depois reaproveita o modelo preparado em memória.
pedir_ajuste <- function(raiz, pasta, pop, chave, key, expo, causa = "naturais", cod = "000") {
  x <- if (causa %in% names(CAUSAS) && codigo_valido(cod)) ler_ajuste(pasta, chave, pop, expo, key, causa, cod) else NULL
  if (!is.null(x)) return(promises::promise_resolve(list(payload = x, do_cache = TRUE, segundos = 0)))
  id <- paste(chave, pop, causa, cod, expo, key, sep = "\r")
  if (!is.null(.pendentes[[id]])) return(.pendentes[[id]])
  p <- promises::future_promise({
    if (!exists("executar_ajuste", mode = "function")) {
      source(file.path(raiz, "R", "utf8.R"))
      for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))
    }
    executar_ajuste(pasta, pop, chave, key, expo, causa, cod)
  }, globals = list(raiz = raiz, pasta = pasta, pop = pop, chave = chave, key = key, expo = expo, causa = causa, cod = cod), seed = NULL)
  assign(id, p, envir = .pendentes)
  # limpa a lista de pendentes ao terminar; o erro, se houver, segue para quem chamou (aqui só se evita o aviso de rejeição sem tratamento)
  promises::catch(promises::finally(p, function() if (exists(id, envir = .pendentes, inherits = FALSE)) rm(list = id, envir = .pendentes)), function(e) NULL)
  p
}
