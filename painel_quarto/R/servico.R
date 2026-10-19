# Serviço de ajuste sob demanda do painel Shiny.
#
# O app não ajusta nada ao abrir: lê o contexto já pronto do cache de dados (R/fontes_remotas.R) e, quando o usuário escolhe um recorte, uma medida
# de calor, uma causa de óbito e o que retirar do ajuste, ajusta só aquele modelo do João (R/modelo_joao.R) e guarda o resultado em disco. O mesmo
# pedido, feito de novo por qualquer usuário, sai do disco. As mesmas funções rodam no processo principal (testes) e nos trabalhadores do pacote future (app).
#
# Pedido = população + causa + retiradas + medida de calor + recorte.
#   causa:     uma das CAUSAS (R/funcoes.R): naturais, todas_sem_covid, todas, externas.
#   retiradas: código de 3 caracteres 0/1, na ordem COVID, meses não consolidados, dias sem clima (ver fora_ajuste() em R/modelo_joao.R).
#              "000" é o modelo padrão (só os dias sem registro no SIM saem do ajuste).
# Cache de ajustes: <cache>/ajustes/<chave>/<pop>_<medida>_<hash de causa, retiradas e recorte>.rds. A chave é a versão dos dados; versão nova,
# pasta nova (atualizar_cache() apaga as pastas das versões antigas). Um ajuste é gravado em arquivo temporário e renomeado, como o contexto.

.servico <- new.env()                       # estado do processo: modelo preparado de cada população

CODIGOS_OPC <- c("000", "001", "010", "011", "100", "101", "110", "111")
opc_de_codigo <- function(cod) { v <- strsplit(cod, "")[[1]] == "1"; list(covid = v[1], nc = v[2], clima = v[3]) }
codigo_valido <- function(cod) is.character(cod) && length(cod) == 1 && !is.na(cod) && cod %in% CODIGOS_OPC

# ---------------------------------------------------------------- preparo do modelo a partir do contexto
preparar_modelo <- function(cx) {
  sem <- semanas(cx$dias)
  g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
  list(cx = cx, Yc = new.env(), b = base_modelo(cx), kt = k_tempo(length(cx$dias)), sem = sem,
       cov_w = as.logical(tapply(cx$covid, g, any)), cbi = new.env())
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

# Ajusta um recorte (chave "local|faixa" ou "local|Todas as idades|raça") para uma medida de calor, uma causa e um conjunto de retiradas;
# devolve o payload da figura.
ajustar_recorte <- function(P, key, expo, causa = "naturais", cod = "000") {
  y <- y_causa(P, causa)[[key]]
  stopifnot(!is.null(y), expo %in% names(EXPOSICOES), codigo_valido(cod))
  r <- ajustar_segmento(y, P$b, cbi_de(P, expo), fora_ajuste(P$cx, opc_de_codigo(cod)), P$kt)
  payload_segmento(r, y, P$sem, P$cov_w)
}

# Dados-base da figura (calendário, clima, sinalizações) mais o que o navegador precisa saber no modo sob demanda: causas, recortes elegíveis
# para cada combinação de causa e retiradas e a distribuição de raça/cor de cada causa. `elig` = elegibilidade(P), lida do disco quando existe.
base_sob_demanda <- function(P, elig = elegibilidade(P)) {
  b <- base_figura1(P$cx, P$kt)
  b$meta$elegiveis <- lapply(elig, function(porcod) lapply(porcod, I))
  b$meta$causas <- as.list(CAUSAS)
  b$meta$sob_demanda <- TRUE
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

# ---------------------------------------------------------------- cache de ajustes em disco
arquivo_ajuste <- function(pasta, chave, pop, expo, key, causa = "naturais", cod = "000")
  file.path(pasta, "ajustes", chave, sprintf("%s_%s_%s.rds", pop, expo, substr(md5_texto(enc2utf8(paste(causa, cod, key, sep = "\r"))), 1, 12)))

ler_ajuste <- function(pasta, chave, pop, expo, key, causa = "naturais", cod = "000") {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key, causa, cod)
  if (!file.exists(f)) return(NULL)
  x <- tryCatch(readRDS(f), error = function(e) NULL)
  if (is.null(x) || !identical(x$key, key) || !identical(x$expo, expo) || !identical(x$causa, causa) || !identical(x$cod, cod)) return(NULL)   # corrompido ou colisão de hash
  x$payload
}

gravar_ajuste <- function(payload, pasta, chave, pop, expo, key, causa = "naturais", cod = "000") {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key, causa, cod)
  dir.create(dirname(f), showWarnings = FALSE, recursive = TRUE)
  tmp <- paste0(f, ".", Sys.getpid(), ".parte")
  saveRDS(list(key = key, expo = expo, causa = causa, cod = cod, pop = pop, chave = chave, payload = payload), tmp)
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
  if (!causa %in% names(CAUSAS) || !codigo_valido(cod)) stop("recorte_invalido: causa ou retiradas fora da lista", call. = FALSE)
  x <- ler_ajuste(pasta, chave, pop, expo, key, causa, cod)
  if (!is.null(x)) return(list(payload = x, do_cache = TRUE, segundos = 0))
  P <- obter_P(pasta, pop, chave)
  if (is.null(P)) stop("dados_mudaram: o cache de dados mudou de versão; recarregue a página", call. = FALSE)
  y <- if (expo %in% names(EXPOSICOES)) y_causa(P, causa)[[key]] else NULL
  if (is.null(y)) stop("recorte_invalido: recorte ou medida de calor fora da lista", call. = FALSE)
  if (sum(y[!fora_ajuste(P$cx, opc_de_codigo(cod))]) < MIN_OBITOS) stop("recorte_invalido: poucos óbitos no ajuste", call. = FALSE)
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
