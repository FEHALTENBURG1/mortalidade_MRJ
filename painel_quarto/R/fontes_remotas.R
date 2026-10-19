# Camada de dados remotos do painel.
#
# Consulta as Releases do GitHub, baixa o silver do SIM e o HAAT do clima, monta o contexto (contexto() de funcoes.R) e guarda em cache no disco.
# O app Shiny só lê o cache (ler_contexto); quem usa a rede é atualizar_cache(), chamada por shiny/atualizar_cache.R (cron) ou em segundo plano.
#
# Fontes (as mesmas do workflow atualizar_painel.yml):
#   SIM   Release "sim-mrj",  arquivo silver_sim_mrj.tar.gz         no repositório com o arquivo mais recente entre PAINEL_SIM_REPOS
#   clima Release "clima-mrj", arquivo haat_diario_municipal.csv    em PAINEL_CLIMA_REPO
# Variáveis de ambiente (todas opcionais):
#   PAINEL_SIM_REPOS, PAINEL_CLIMA_REPO, GITHUB_PAT (ou GITHUB_TOKEN: só para subir o limite da API, que é de 60 consultas por hora sem token),
#   PAINEL_GITHUB_API e PAINEL_GITHUB_DOWNLOAD (trocam os endereços base; usadas nos testes com um servidor local).
#
# Garantias do cache:
#   - versão nova só entra depois de baixada, com o tamanho conferido, e processada sem erro; antes disso o cache anterior continua valendo;
#   - os arquivos são gravados com outro nome e renomeados no fim (a troca é atômica no mesmo disco);
#   - um bloqueio em disco evita duas atualizações ao mesmo tempo (cron e app); bloqueio com mais de 3 horas é considerado abandonado;
#   - sem acesso ao GitHub, o cache existente é mantido.

ou <- function(a, b) if (is.null(a) || !length(a)) b else a

config_fontes <- function() list(
  api        = sub("/+$", "", Sys.getenv("PAINEL_GITHUB_API", "https://api.github.com")),
  baixar     = sub("/+$", "", Sys.getenv("PAINEL_GITHUB_DOWNLOAD", "https://github.com")),
  repos_sim  = strsplit(trimws(Sys.getenv("PAINEL_SIM_REPOS", "FEHALTENBURG1/mortalidade_MRJ FEHALTENBURG1/Dados_clima_MRJ")), "[[:space:]]+")[[1]],
  repo_clima = Sys.getenv("PAINEL_CLIMA_REPO", "FEHALTENBURG1/Dados_clima_MRJ"),
  tag_sim = "sim-mrj", asset_sim = "silver_sim_mrj.tar.gz",
  tag_clima = "clima-mrj", asset_clima = "haat_diario_municipal.csv",
  token      = Sys.getenv("GITHUB_PAT", Sys.getenv("GITHUB_TOKEN", "")))

# ---------------------------------------------------------------- rede
# Baixa uma URL para um arquivo, com tentativas. Devolve TRUE/FALSE (nunca erro).
baixar_url <- function(url, destino, cabecalhos = NULL, tentativas = 3, espera = 5, timeout = 3600) {
  antigo <- options(timeout = timeout); on.exit(options(antigo), add = TRUE)
  for (i in seq_len(tentativas)) {
    ok <- tryCatch(suppressWarnings(utils::download.file(url, destino, mode = "wb", quiet = TRUE, method = "libcurl", headers = cabecalhos)) == 0,
                   error = function(e) FALSE)
    if (isTRUE(ok) && file.exists(destino) && file.size(destino) > 0) return(TRUE)
    unlink(destino)
    if (i < tentativas) Sys.sleep(espera)
  }
  FALSE
}

# Dados do arquivo na Release (id, tamanho, data de atualização e endereço de download), ou NULL se a Release ou o arquivo não existem.
versao_remota <- function(repo, tag, asset, cfg = config_fontes()) {
  tmp <- tempfile(fileext = ".json"); on.exit(unlink(tmp), add = TRUE)
  cab <- c(Accept = "application/vnd.github+json", `User-Agent` = "painel-mrj", if (nzchar(cfg$token)) c(Authorization = paste("Bearer", cfg$token)))
  if (!baixar_url(sprintf("%s/repos/%s/releases/tags/%s", cfg$api, repo, tag), tmp, cab, tentativas = 2, espera = 1)) return(NULL)
  rel <- tryCatch(jsonlite::fromJSON(tmp, simplifyVector = FALSE), error = function(e) NULL)
  a <- Filter(function(x) identical(x$name, asset), ou(rel$assets, list()))
  if (!length(a)) return(NULL)
  a <- a[[1]]
  list(repo = repo, tag = tag, asset = asset, id = as.character(a$id), tamanho = as.numeric(a$size),
       atualizado = ou(a$updated_at, ou(a$created_at, "")),
       url = sprintf("%s/%s/releases/download/%s/%s", cfg$baixar, repo, tag, asset))
}

# Versões atuais do silver do SIM (repositório com o arquivo mais recente) e do HAAT. NULL se alguma das duas não puder ser lida.
versoes_remotas <- function(cfg = config_fontes()) {
  sims <- Filter(Negate(is.null), lapply(cfg$repos_sim, function(r) versao_remota(r, cfg$tag_sim, cfg$asset_sim, cfg)))
  clima <- versao_remota(cfg$repo_clima, cfg$tag_clima, cfg$asset_clima, cfg)
  if (!length(sims) || is.null(clima)) return(NULL)
  sim <- sims[[order(vapply(sims, function(s) s$atualizado, ""), decreasing = TRUE)[1]]]     # datas ISO 8601 em UTC ordenam como texto
  list(sim = sim, clima = clima)
}

# ---------------------------------------------------------------- chave e arquivos do cache
md5_texto <- function(x) { f <- tempfile(); on.exit(unlink(f)); writeLines(x, f, useBytes = TRUE); unname(tools::md5sum(f)) }

# A chave muda quando muda qualquer um dos dois arquivos de origem ou o código das regras (funcoes.R): regra nova invalida o cache.
chave_cache <- function(v, arquivo_regras) {
  s <- paste(v$sim$repo, v$sim$id, v$sim$tamanho, v$sim$atualizado, v$clima$repo, v$clima$id, v$clima$tamanho, v$clima$atualizado,
             unname(tools::md5sum(arquivo_regras)))
  substr(md5_texto(s), 1, 12)
}

caminho_meta <- function(pasta, pop) file.path(pasta, sprintf("meta_%s.json", pop))
meta_cache <- function(pasta, pop) {
  f <- caminho_meta(pasta, pop)
  if (!file.exists(f)) return(NULL)
  tryCatch(jsonlite::fromJSON(f, simplifyVector = TRUE), error = function(e) NULL)
}

# Lê o contexto em cache. Devolve list(cx, meta) ou NULL. Tenta duas vezes: se uma atualização trocar o arquivo no meio da leitura, a segunda leitura pega o novo.
ler_contexto <- function(pasta, pop = "res") {
  for (i in 1:2) {
    m <- meta_cache(pasta, pop)
    if (is.null(m)) return(NULL)
    f <- file.path(pasta, sprintf("contexto_%s_%s.rds", pop, m$chave))
    x <- if (file.exists(f)) tryCatch(readRDS(f), error = function(e) NULL) else NULL
    if (!is.null(x)) return(x)
    Sys.sleep(1)
  }
  NULL
}

# ---------------------------------------------------------------- bloqueio (uma atualização por vez)
pegar_bloqueio <- function(pasta, max_horas = 3) {
  dir <- file.path(pasta, "bloqueio")
  if (dir.exists(dir)) {
    if (as.numeric(difftime(Sys.time(), file.mtime(dir), units = "hours")) < max_horas) return(NULL)
    unlink(dir, recursive = TRUE)                                      # abandonado (processo morto no meio da atualização)
  }
  if (!dir.create(dir, showWarnings = FALSE)) return(NULL)             # dir.create é atômico: só um processo consegue
  writeLines(as.character(Sys.getpid()), file.path(dir, "pid"))
  dir
}

gravar_status <- function(pasta, status, detalhe = "") {
  try(jsonlite::write_json(list(status = status, quando = format(Sys.time(), "%Y-%m-%d %H:%M:%S"), detalhe = detalhe),
                           file.path(pasta, "ultima_tentativa.json"), auto_unbox = TRUE), silent = TRUE)
}

# ---------------------------------------------------------------- atualização
# Garante que o cache de cada população em `pops` ("res", "todos") corresponde às versões atuais das Releases.
# Devolve list(status, chave, tem_cache, detalhe). status:
#   "atual"       o cache já estava na versão das Releases
#   "atualizado"  baixou, processou e trocou o cache
#   "offline"     GitHub inacessível (ou sem o arquivo): o cache existente foi mantido
#   "ocupado"     outra atualização está em andamento
#   "falhou"      erro no download ou no processamento: o cache anterior foi mantido
atualizar_cache <- function(pasta, pops = c("res", "todos"), cnes, arquivo_regras, forcar = FALSE, cfg = config_fontes(),
                            log = function(...) cat(format(Sys.time(), "%H:%M:%S"), ..., "\n")) {
  dir.create(pasta, showWarnings = FALSE, recursive = TRUE)
  tem_cache <- function() all(vapply(pops, function(p) !is.null(meta_cache(pasta, p)), TRUE))
  fim <- function(status, chave = NA_character_, detalhe = "") {
    gravar_status(pasta, status, detalhe); log("status:", status, if (nzchar(detalhe)) paste0("(", detalhe, ")"))
    list(status = status, chave = chave, tem_cache = tem_cache(), detalhe = detalhe)
  }

  log("consultando as Releases...")
  v <- versoes_remotas(cfg)
  if (is.null(v)) return(fim("offline", detalhe = "não foi possível ler as Releases do SIM e do clima"))
  chave <- chave_cache(v, arquivo_regras)
  log(sprintf("SIM: %s (%s, %.0f MB) | clima: %s (%s)", v$sim$repo, v$sim$atualizado, v$sim$tamanho / 1e6, v$clima$repo, v$clima$atualizado))

  em_dia <- all(vapply(pops, function(p) identical(meta_cache(pasta, p)$chave, chave), TRUE))
  if (em_dia && !forcar) return(fim("atual", chave))

  bloq <- pegar_bloqueio(pasta)
  if (is.null(bloq)) return(fim("ocupado", chave, "outra atualização em andamento"))
  trabalho <- file.path(pasta, paste0("tmp_", Sys.getpid()))
  on.exit({ unlink(bloq, recursive = TRUE); unlink(trabalho, recursive = TRUE) }, add = TRUE)
  dir.create(trabalho, showWarnings = FALSE)

  erro <- tryCatch({
    tar <- file.path(trabalho, "silver.tar.gz"); haat <- file.path(trabalho, "haat.csv")
    log("baixando o silver do SIM...")
    if (!baixar_url(v$sim$url, tar)) stop("download do silver do SIM falhou")
    if (file.size(tar) != v$sim$tamanho) stop(sprintf("silver com %s bytes; o GitHub informa %s", file.size(tar), v$sim$tamanho))
    log("baixando o HAAT do clima...")
    if (!baixar_url(v$clima$url, haat)) stop("download do HAAT falhou")
    if (file.size(haat) != v$clima$tamanho) stop(sprintf("HAAT com %s bytes; o GitHub informa %s", file.size(haat), v$clima$tamanho))

    log("extraindo os óbitos por ocorrência...")
    nomes <- utils::untar(tar, list = TRUE)
    # Só os arquivos (nomes que não terminam em "/"): passar também a pasta faria o tar reclamar de nomes repetidos, porque a pasta já extrai tudo.
    sel <- grep("^(\\./)?silver/sim/ocorrencia_mrj/.*[^/]$", nomes, value = TRUE)
    if (!length(sel)) stop("silver/sim/ocorrencia_mrj não encontrado no arquivo")
    if (any(grepl("(^|/)\\.\\.(/|$)", sel)) || any(startsWith(sel, "/"))) stop("caminho suspeito dentro do arquivo do SIM")
    st <- suppressWarnings(utils::untar(tar, files = sel, exdir = file.path(trabalho, "x")))
    silver <- file.path(trabalho, "x", "silver")
    n_ok <- sum(file.exists(file.path(trabalho, "x", sub("^\\./", "", sel))))
    if (!identical(as.integer(st), 0L) || n_ok != length(sel)) stop(sprintf("extração incompleta do silver do SIM (%d de %d arquivos)", n_ok, length(sel)))
    unlink(tar)

    for (pop in pops) {
      log("montando o contexto:", pop)
      cx <- contexto(silver, haat, cnes, pop)
      cx$d_todas_causas <- NULL; cx$cl_completo <- NULL                # o painel só usa os óbitos naturais
      meta <- list(chave = chave, pop = pop, repo_sim = v$sim$repo, sim_atualizado = v$sim$atualizado, clima_atualizado = v$clima$atualizado,
                   gerado_em = format(Sys.time(), "%Y-%m-%d %H:%M"), inicio = as.character(cx$inicio), fim = as.character(cx$fim),
                   n_obitos = nrow(cx$d), n_dias = length(cx$dias))
      destino <- file.path(pasta, sprintf("contexto_%s_%s.rds", pop, chave))
      saveRDS(list(cx = cx, meta = meta), paste0(destino, ".parte")); file.rename(paste0(destino, ".parte"), destino)
      jsonlite::write_json(meta, paste0(caminho_meta(pasta, pop), ".parte"), auto_unbox = TRUE)
      file.rename(paste0(caminho_meta(pasta, pop), ".parte"), caminho_meta(pasta, pop))     # só agora o app passa a ler a versão nova
      unlink(setdiff(Sys.glob(file.path(pasta, sprintf("contexto_%s_*.rds", pop))), destino))
    }
    if (exists("limpar_ajustes_antigos", mode = "function")) limpar_ajustes_antigos(pasta, chave)      # ajustes do app Shiny (R/servico.R) são por versão
    NULL
  }, error = function(e) conditionMessage(e))

  if (!is.null(erro)) return(fim("falhou", chave, erro))
  fim("atualizado", chave)
}
