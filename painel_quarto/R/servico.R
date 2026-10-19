# Serviço de ajuste sob demanda do painel Shiny.
#
# O app não ajusta nada ao abrir: lê o contexto já pronto do cache de dados (R/fontes_remotas.R) e, quando o usuário escolhe um recorte e uma medida
# de calor, ajusta só aquele modelo do João (R/modelo_joao.R) e guarda o resultado em disco. O mesmo recorte pedido de novo, por qualquer
# usuário, sai do disco. As mesmas funções rodam no processo principal (testes) e nos trabalhadores do pacote future (app).
#
# Cache de ajustes: <cache>/ajustes/<chave>/<pop>_<medida>_<hash do recorte>.rds. A chave é a versão dos dados; versão nova, pasta nova
# (atualizar_cache() apaga as pastas das versões antigas). Um ajuste é gravado em arquivo temporário e renomeado, como o contexto.

.servico <- new.env()                       # estado do processo: modelo preparado de cada população

# ---------------------------------------------------------------- preparo do modelo a partir do contexto
preparar_modelo <- function(cx) {
  Y <- series_segmentos(cx$d, cx$dias)
  no_ajuste <- vapply(Y, function(y) sum(y[!cx$sem_registro]), 0)
  sem <- semanas(cx$dias)
  g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
  list(cx = cx, Y = Y, elegiveis = names(Y)[no_ajuste >= MIN_OBITOS], b = base_modelo(cx), kt = k_tempo(length(cx$dias)), sem = sem,
       cov_w = as.logical(tapply(cx$covid, g, any)), cbi = new.env())
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

# Ajusta um recorte (chave "local|faixa" ou "local|Todas as idades|raça") para uma medida de calor e devolve o payload da figura.
ajustar_recorte <- function(P, key, expo) {
  y <- P$Y[[key]]
  stopifnot(!is.null(y), expo %in% names(EXPOSICOES))
  r <- ajustar_segmento(y, P$b, cbi_de(P, expo), P$cx$sem_registro, P$kt)
  payload_segmento(r, y, P$sem, P$cov_w)
}

# Dados-base da figura (calendário, clima, sinalizações) mais o que o navegador precisa saber no modo sob demanda.
base_sob_demanda <- function(P) {
  b <- base_figura1(P$cx, P$kt)
  b$meta$elegiveis <- I(P$elegiveis)
  b$meta$sob_demanda <- TRUE
  b$meta$dados <- list(chave = P$meta$chave, sim_atualizado = P$meta$sim_atualizado, clima_atualizado = P$meta$clima_atualizado, repo_sim = P$meta$repo_sim,
                    gerado_em = P$meta$gerado_em)
  b
}

# ---------------------------------------------------------------- cache de ajustes em disco
arquivo_ajuste <- function(pasta, chave, pop, expo, key)
  file.path(pasta, "ajustes", chave, sprintf("%s_%s_%s.rds", pop, expo, substr(md5_texto(enc2utf8(key)), 1, 12)))

ler_ajuste <- function(pasta, chave, pop, expo, key) {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key)
  if (!file.exists(f)) return(NULL)
  x <- tryCatch(readRDS(f), error = function(e) NULL)
  if (is.null(x) || !identical(x$key, key) || !identical(x$expo, expo)) return(NULL)      # arquivo corrompido ou colisão de hash
  x$payload
}

gravar_ajuste <- function(payload, pasta, chave, pop, expo, key) {
  f <- arquivo_ajuste(pasta, chave, pop, expo, key)
  dir.create(dirname(f), showWarnings = FALSE, recursive = TRUE)
  tmp <- paste0(f, ".", Sys.getpid(), ".parte")
  saveRDS(list(key = key, expo = expo, pop = pop, chave = chave, payload = payload), tmp)
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
executar_ajuste <- function(pasta, pop, chave, key, expo) {
  x <- ler_ajuste(pasta, chave, pop, expo, key)
  if (!is.null(x)) return(list(payload = x, do_cache = TRUE, segundos = 0))
  P <- obter_P(pasta, pop, chave)
  if (is.null(P)) stop("dados_mudaram: o cache de dados mudou de versão; recarregue a página", call. = FALSE)
  if (!key %in% P$elegiveis || !expo %in% names(EXPOSICOES)) stop("recorte_invalido: recorte ou medida de calor fora da lista", call. = FALSE)
  t0 <- Sys.time()
  x <- ajustar_recorte(P, key, expo)
  gravar_ajuste(x, pasta, chave, pop, expo, key)
  list(payload = x, do_cache = FALSE, segundos = as.numeric(difftime(Sys.time(), t0, units = "secs")))
}

# ---------------------------------------------------------------- pedidos assíncronos (app): trabalhadores do future, sem repetir o mesmo pedido
.pendentes <- new.env()

# Devolve uma promessa com o resultado de executar_ajuste(). Pedidos iguais em andamento compartilham a mesma promessa.
# Pede ao future um trabalhador que carrega o código de `raiz` na primeira vez e depois reaproveita o modelo preparado em memória.
pedir_ajuste <- function(raiz, pasta, pop, chave, key, expo) {
  x <- ler_ajuste(pasta, chave, pop, expo, key)
  if (!is.null(x)) return(promises::promise_resolve(list(payload = x, do_cache = TRUE, segundos = 0)))
  id <- paste(chave, pop, expo, key, sep = "\r")
  if (!is.null(.pendentes[[id]])) return(.pendentes[[id]])
  p <- promises::future_promise({
    if (!exists("executar_ajuste", mode = "function")) {
      source(file.path(raiz, "R", "utf8.R"))
      for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))
    }
    executar_ajuste(pasta, pop, chave, key, expo)
  }, globals = list(raiz = raiz, pasta = pasta, pop = pop, chave = chave, key = key, expo = expo), seed = NULL)
  assign(id, p, envir = .pendentes)
  # limpa a lista de pendentes ao terminar; o erro, se houver, segue para quem chamou (aqui só se evita o aviso de rejeição sem tratamento)
  promises::catch(promises::finally(p, function() if (exists(id, envir = .pendentes, inherits = FALSE)) rm(list = id, envir = .pendentes)), function(e) NULL)
  p
}
