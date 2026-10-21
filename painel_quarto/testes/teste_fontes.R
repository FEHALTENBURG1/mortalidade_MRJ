#!/usr/bin/env Rscript
# Testa a camada de dados remotos (R/fontes_remotas.R) contra um servidor HTTP local que imita a API e os downloads das Releases do GitHub.
#
# Uso, a partir da pasta do projeto:
#   PAINEL_TESTE_TAR=/caminho/silver_sim_mrj.tar.gz PAINEL_TESTE_HAAT=/caminho/haat_diario_municipal.csv \
#   PAINEL_TESTE_SILVER=/caminho/silver_extraido  Rscript testes/teste_fontes.R
# Sem as variáveis, roda só os testes que não precisam de dados. PAINEL_TESTE_SILVER (opcional) é o silver já extraído, para comparar o cache com
# a leitura direta. Precisa de python3 (http.server). Demora alguns minutos, porque monta o contexto várias vezes.

invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
Sys.setenv(no_proxy = "127.0.0.1,localhost", NO_PROXY = "127.0.0.1,localhost")      # o servidor de teste não passa por proxy
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(dirname(normalizePath(a[1]))) else getwd() })
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))
regras <- file.path(raiz, "R", "funcoes.R"); cnes <- file.path(raiz, "dados_auxiliares", "cnes_estab.csv")

falhas <- character(0)
checar <- function(nome, cond) { ok <- isTRUE(cond); cat(sprintf("%s %s\n", if (ok) "ok    " else "FALHOU", nome)); if (!ok) falhas <<- c(falhas, nome) }
silencio <- function(...) invisible(NULL)

# ---------------------------------------------------------------- sem dados: chave e bloqueio
v1 <- list(sim = list(repo = "a/b", id = "1", tamanho = 10, atualizado = "2026-01-01T00:00:00Z"), clima = list(repo = "a/c", id = "2", tamanho = 5, atualizado = "2026-01-02T00:00:00Z"))
v2 <- v1; v2$sim$atualizado <- "2026-02-01T00:00:00Z"
v3 <- v1; v3$clima$id <- "3"
checar("chave: mesma versão dá a mesma chave", identical(chave_cache(v1, regras), chave_cache(v1, regras)))
checar("chave: muda com a data do SIM", chave_cache(v1, regras) != chave_cache(v2, regras))
checar("chave: muda com o arquivo do clima", chave_cache(v1, regras) != chave_cache(v3, regras))
regras2 <- tempfile(fileext = ".R"); invisible(file.copy(regras, regras2)); cat("# mudou\n", file = regras2, append = TRUE)
checar("chave: muda com o código das regras", chave_cache(v1, regras) != chave_cache(v1, regras2))

p0 <- tempfile("cache0_"); dir.create(p0)
checar("cache vazio: ler_contexto devolve NULL", is.null(ler_contexto(p0, "res")))
b1 <- pegar_bloqueio(p0)
checar("bloqueio: o primeiro processo consegue", !is.null(b1))
checar("bloqueio: o segundo não consegue enquanto o primeiro segura", is.null(pegar_bloqueio(p0)))
Sys.setFileTime(b1, Sys.time() - 4 * 3600)
checar("bloqueio: com mais de 3 horas é considerado abandonado", !is.null(pegar_bloqueio(p0)))

# ---------------------------------------------------------------- com dados: servidor local imitando o GitHub
tar_in <- Sys.getenv("PAINEL_TESTE_TAR"); haat_in <- Sys.getenv("PAINEL_TESTE_HAAT"); silver_dir <- Sys.getenv("PAINEL_TESTE_SILVER")
if (!nzchar(tar_in) || !nzchar(haat_in) || !file.exists(tar_in) || !file.exists(haat_in)) {
  cat("PULADO: defina PAINEL_TESTE_TAR e PAINEL_TESTE_HAAT para testar o download e o cache.\n")
} else {
  mock <- tempfile("mock_"); dir.create(mock)
  repo_sim <- "FEHALTENBURG1/mortalidade_MRJ"; repo_clima <- "FEHALTENBURG1/Dados_clima_MRJ"
  dl <- function(repo, tag) file.path(mock, repo, "releases", "download", tag)
  for (d in c(dl(repo_sim, "sim-mrj"), dl(repo_clima, "clima-mrj"))) dir.create(d, recursive = TRUE)
  file.symlink(normalizePath(tar_in), file.path(dl(repo_sim, "sim-mrj"), "silver_sim_mrj.tar.gz"))
  file.symlink(normalizePath(haat_in), file.path(dl(repo_clima, "clima-mrj"), "haat_diario_municipal.csv"))
  # Só o repositório de mortalidade tem o silver; o de clima responde 404 para sim-mrj (o código deve tolerar isso).
  api <- function(repo, tag, asset, tam, quando, id) {
    d <- file.path(mock, "repos", repo, "releases", "tags"); dir.create(d, recursive = TRUE, showWarnings = FALSE)
    writeLines(as.character(jsonlite::toJSON(list(tag_name = tag, assets = list(list(name = asset, id = id, size = tam, updated_at = quando))), auto_unbox = TRUE)), file.path(d, tag))
  }
  publicar <- function(quando_sim, id_sim, tam_sim = file.size(tar_in)) {
    api(repo_sim, "sim-mrj", "silver_sim_mrj.tar.gz", tam_sim, quando_sim, id_sim)
    api(repo_clima, "clima-mrj", "haat_diario_municipal.csv", file.size(haat_in), "2026-10-01T10:00:00Z", 77)
  }
  porta <- sample(20000:29000, 1); log_srv <- tempfile("srv_", fileext = ".log"); pid <- NA
  subir <- function() {
    pid <<- system(sprintf("python3 -I -m http.server %d --bind 127.0.0.1 --directory %s > %s 2>&1 & echo $!", porta, shQuote(mock), shQuote(log_srv)), intern = TRUE)
    for (i in 1:50) { if (suppressWarnings(tryCatch(utils::download.file(sprintf("http://127.0.0.1:%d/", porta), tempfile(), quiet = TRUE), error = function(e) 1)) == 0) return(invisible()); Sys.sleep(0.2) }
    stop("servidor de teste não subiu")
  }
  derrubar <- function() { if (!is.na(pid)) system(paste("kill", pid), ignore.stderr = TRUE); pid <<- NA }
  baixou_tar <- function() sum(grepl("GET .*silver_sim_mrj.tar.gz", readLines(log_srv, warn = FALSE)))
  Sys.setenv(PAINEL_GITHUB_API = sprintf("http://127.0.0.1:%d", porta), PAINEL_GITHUB_DOWNLOAD = sprintf("http://127.0.0.1:%d", porta),
             PAINEL_SIM_REPOS = paste(repo_sim, repo_clima), PAINEL_CLIMA_REPO = repo_clima)

  publicar("2026-10-01T09:00:00Z", 11)
  subir()
  pasta <- tempfile("cache_"); dir.create(pasta)
  rodar <- function(pops = c("res", "todos"), ...) atualizar_cache(pasta, pops, cnes, regras, log = silencio, ...)
  arquivos <- function(pop) basename(Sys.glob(file.path(pasta, sprintf("contexto_%s_*.rds", pop))))

  # 1. primeira carga
  r1 <- rodar()
  checar("1ª carga: status atualizado", identical(r1$status, "atualizado"))
  checar("1ª carga: um arquivo de contexto por população", length(arquivos("res")) == 1 && length(arquivos("todos")) == 1)
  checar("1ª carga: baixou o silver uma vez", baixou_tar() == 1)
  checar("1ª carga: sem sobras (bloqueio, pasta de trabalho, .parte)", !dir.exists(file.path(pasta, "bloqueio")) && !length(Sys.glob(file.path(pasta, "tmp_*"))) && !length(Sys.glob(file.path(pasta, "*.parte"))))
  x <- ler_contexto(pasta, "res")
  checar("1ª carga: ler_contexto devolve o contexto com metadados", !is.null(x) && x$meta$pop == "res" && nrow(x$cx$d) == x$meta$n_obitos && nrow(x$cx$d) > 100000)
  checar("1ª carga: cache sem as tabelas que o painel não usa", is.null(x$cx$d_todas_causas) && is.null(x$cx$cl_completo))
  checar("1ª carga: traz os óbitos de outras causas (d_extra) com a marca de COVID", is.data.frame(x$cx$d_extra) && nrow(x$cx$d_extra) > 0 && all(c(COLUNAS_SERIE, "covid", "grupo", "cid") %in% names(x$cx$d_extra)) && !"cid4" %in% names(x$cx$d_extra))
  xt <- ler_contexto(pasta, "todos")
  checar("1ª carga: 'todos' tem mais óbitos que 'res'", nrow(xt$cx$d) > nrow(x$cx$d))
  checar("1ª carga: rótulos com acento preservados", all(c("Domicílio", "Hospital") %in% as.character(unique(x$cx$d$local))))
  if (nzchar(silver_dir) && dir.exists(silver_dir)) {
    direto <- contexto(silver_dir, haat_in, cnes, "res")
    checar("cache igual à leitura direta (óbitos naturais)", isTRUE(all.equal(x$cx$d, direto$d)))
    dd <- direto$d_todas_causas
    checar("cache igual à leitura direta (todas as causas: contagens e COVID)", nrow(obitos_causa(x$cx, "todas")) == nrow(dd) && nrow(x$cx$d_extra) == sum(!dd$natural) &&
             sum(x$cx$d_extra$covid) == sum(dd$grupo == "covid") && sum(dd$grupo == "covid") == sum(eh_covid(dd$cid4)) && nrow(obitos_causa(x$cx, "externas")) == sum(dd$grupo == "externa") &&
             nrow(obitos_causa(x$cx, "todas_sem_covid")) == sum(dd$grupo != "covid"))
    checar("cache igual à leitura direta (reconciliação das causas soma o total de óbitos elegíveis)", isTRUE(all.equal(x$cx$reconc, direto$reconc)) && x$cx$reconc$total == nrow(dd) && sum(x$cx$reconc$grupos$n) == nrow(dd))
    checar("cache igual à leitura direta (período, meses não consolidados, dias sem registro, clima)",
           identical(x$cx$fim, direto$fim) && identical(x$cx$meses_nc, direto$meses_nc) && identical(x$cx$sem_registro, direto$sem_registro) && isTRUE(all.equal(x$cx$clima, direto$clima)))
  }

  # 2. mesma versão: não baixa de novo
  m_antes <- file.mtime(file.path(pasta, arquivos("res")))
  r2 <- rodar()
  checar("2ª chamada: status atual", identical(r2$status, "atual"))
  checar("2ª chamada: não baixou de novo e não regravou o cache", baixou_tar() == 1 && identical(m_antes, file.mtime(file.path(pasta, arquivos("res")))))
  r2f <- rodar(pops = "res", forcar = TRUE)
  checar("forçar: refaz mesmo sem versão nova", identical(r2f$status, "atualizado") && baixou_tar() == 2)

  # 3. versão nova no GitHub: troca o cache e apaga o antigo
  chave_antiga <- meta_cache(pasta, "res")$chave
  dir.create(file.path(pasta, "ajustes", chave_antiga), recursive = TRUE); saveRDS(1, file.path(pasta, "ajustes", chave_antiga, "res_horas_x.rds"))    # ajuste do app Shiny na versão antiga
  publicar("2026-10-10T09:00:00Z", 12)
  r3 <- rodar()
  checar("versão nova: status atualizado", identical(r3$status, "atualizado"))
  checar("versão nova: chave mudou e só resta o arquivo novo", meta_cache(pasta, "res")$chave != chave_antiga && length(arquivos("res")) == 1 && !grepl(chave_antiga, arquivos("res")))
  checar("versão nova: ajustes da versão antiga (app Shiny) foram apagados", !dir.exists(file.path(pasta, "ajustes", chave_antiga)))
  checar("versão nova: meta traz a data da Release", identical(meta_cache(pasta, "res")$sim_atualizado, "2026-10-10T09:00:00Z"))

  # 4. download com tamanho diferente do informado: falha sem estragar o cache
  chave_boa <- meta_cache(pasta, "res")$chave
  publicar("2026-10-15T09:00:00Z", 13, tam_sim = file.size(tar_in) + 1)
  r4 <- rodar()
  checar("tamanho errado: status falhou", identical(r4$status, "falhou"))
  checar("tamanho errado: cache anterior intacto e legível", identical(meta_cache(pasta, "res")$chave, chave_boa) && !is.null(ler_contexto(pasta, "res")))
  checar("tamanho errado: sem bloqueio nem pasta de trabalho abandonados", !dir.exists(file.path(pasta, "bloqueio")) && !length(Sys.glob(file.path(pasta, "tmp_*"))))

  # 5. GitHub fora do ar: mantém o cache
  derrubar()
  r5 <- rodar()
  checar("GitHub fora do ar: status offline com cache", identical(r5$status, "offline") && isTRUE(r5$tem_cache))
  checar("GitHub fora do ar: cache continua legível", !is.null(ler_contexto(pasta, "res")))
  p_vazia <- tempfile("cache_vazio_"); dir.create(p_vazia)
  r5b <- atualizar_cache(p_vazia, "res", cnes, regras, log = silencio)
  checar("GitHub fora do ar e sem cache: offline sem cache", identical(r5b$status, "offline") && !isTRUE(r5b$tem_cache))

  # 6. bloqueio ativo: outra atualização em andamento
  subir(); publicar("2026-10-16T09:00:00Z", 14)
  dir.create(file.path(pasta, "bloqueio"))
  r6 <- rodar(pops = "res")
  checar("bloqueio recente: status ocupado, cache intacto", identical(r6$status, "ocupado") && identical(meta_cache(pasta, "res")$chave, chave_boa) && dir.exists(file.path(pasta, "bloqueio")))
  Sys.setFileTime(file.path(pasta, "bloqueio"), Sys.time() - 4 * 3600)
  r7 <- rodar(pops = "res")
  checar("bloqueio abandonado: atualiza", identical(r7$status, "atualizado") && !dir.exists(file.path(pasta, "bloqueio")))
  checar("status da última tentativa gravado", identical(jsonlite::fromJSON(file.path(pasta, "ultima_tentativa.json"))$status, "atualizado"))
  cat(sprintf("tamanho do cache em disco: res %.0f MB, todos %.0f MB\n", file.size(file.path(pasta, arquivos("res"))) / 1e6, file.size(file.path(pasta, arquivos("todos"))) / 1e6))

  # 8. script de linha de comando (o que o cron chama) e seus códigos de saída
  rscript <- file.path(R.home("bin"), "Rscript")
  cli <- function(...) suppressWarnings(system2(rscript, c(shQuote(file.path(raiz, "shiny", "atualizar_cache.R")), ...), stdout = FALSE, stderr = FALSE))
  checar("script: cache em dia sai com código 0", cli("--cache", shQuote(pasta), "--pop", "res") == 0)
  checar("script: população inválida sai com código diferente de 0", cli("--cache", shQuote(pasta), "--pop", "xyz") != 0)
  derrubar()                                   # on.exit() no nível principal do script não executa: encerra o servidor de teste aqui
  checar("script: GitHub fora do ar, com cache, sai com código 0", cli("--cache", shQuote(pasta), "--pop", "res") == 0)
  checar("script: GitHub fora do ar, sem cache, sai com código 1", cli("--cache", shQuote(p_vazia), "--pop", "res") == 1)
}

cat(if (length(falhas)) sprintf("\nFALHAS (%d): %s\n", length(falhas), paste(falhas, collapse = "; ")) else "\nFALHAS: nenhuma\n")
quit(save = "no", status = if (length(falhas)) 1L else 0L)
