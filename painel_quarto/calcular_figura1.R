#!/usr/bin/env Rscript
# Calcula a Figura 1 do painel (óbitos observados x esperados sem calor, modelo do João por segmento) e grava saida/figura1_<pop>.json.
#
# Uso (a partir da pasta do projeto):
#   Rscript calcular_figura1.R --silver entrada/sim/silver --haat entrada/haat_diario_municipal.csv [--pop res] [--saida saida] [--cores 2]
#
# --silver  pasta silver do data lake do SIM (contém sim/ocorrencia_mrj/ano_arquivo=*/part-0.parquet)
# --haat    haat_diario_municipal.csv (clima diário por município, Release clima-mrj)
# --pop     res (residentes que morreram no Rio, padrão) ou todos (todos os óbitos ocorridos no Rio)
# --reusar  não reajusta os modelos: reaproveita saida/modelos_<pop>.rds (útil para mudar só o texto ou o formato do JSON)
# --cores   processos em paralelo (padrão: metade dos núcleos; no Windows sempre 1)

args <- commandArgs(trailingOnly = TRUE)
opcao <- function(nome, padrao = NULL) { i <- match(paste0("--", nome), args); if (is.na(i)) padrao else args[i + 1] }
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(normalizePath(a[1])) else getwd() })
silver <- opcao("silver"); haat <- opcao("haat")
if (is.null(silver) || is.null(haat)) stop("Informe --silver e --haat (ver o cabeçalho deste script).")
pop   <- opcao("pop", "res")
saida <- opcao("saida", file.path(raiz, "saida"))
cnes  <- opcao("cnes", file.path(raiz, "dados_auxiliares", "cnes_estab.csv"))
reusar <- "--reusar" %in% args     # só refaz o JSON a partir dos ajustes já gravados em saida/modelos_<pop>.rds
cores <- as.integer(opcao("cores", max(1, floor(parallel::detectCores() / 2))))
if (.Platform$OS.type == "windows") cores <- 1L
dir.create(saida, showWarnings = FALSE, recursive = TRUE)
Sys.setenv(OMP_NUM_THREADS = "1")

# Os rótulos com acento (Domicílio, Via pública...) precisam sair em UTF-8 mesmo em sessões com locale "C": por isso fonte_utf8() em vez de source().
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "modelo_joao.R", "exportar.R")) fonte_utf8(file.path(raiz, "R", f))
agora <- function() format(Sys.time(), "%H:%M:%S")

cat(agora(), "lendo óbitos e clima...\n")
cx <- contexto(silver, haat, cnes, pop)
cat(sprintf("%s período %s a %s (%d dias) | óbitos naturais %d | dias sem registro no SIM %d | dias de mês não consolidado %d\n", agora(),
            cx$inicio, cx$fim, length(cx$dias), nrow(cx$d), sum(cx$sem_registro), sum(cx$nao_consolidado)))
cat("meses com registro não consolidado:", paste(format(cx$meses_nc, "%Y-%m"), collapse = ", "), "\n")

Y <- series_segmentos(cx$d, cx$dias)
fora <- fora_ajuste(cx, opc_de_codigo(COD_PADRAO))          # ajuste principal: sem os dias sem registro, os meses não consolidados e os dias sem clima (e os 10 seguintes)
cat(sprintf("%s ajuste principal (código %s): %d dias no ajuste, %d fora\n", agora(), COD_PADRAO, sum(!fora), sum(fora)))
no_ajuste <- vapply(Y, function(y) sum(y[!fora]), 0)
Y <- Y[no_ajuste >= MIN_OBITOS]
cat(sprintf("%s %d segmentos com pelo menos %d óbitos no ajuste\n", agora(), length(Y), MIN_OBITOS))

b <- base_modelo(cx); kt <- k_tempo(length(cx$dias))
cat("nós do spline de tempo:", kt, "\n")
rds <- file.path(saida, sprintf("modelos_%s.rds", pop))
reaproveitou <- reusar && file.exists(rds)
if (reaproveitou) {
  cat("reaproveitando os ajustes de", rds, "\n")
  ajustes <- readRDS(rds)$ajustes
  Y <- Y[names(ajustes[[1]])]
} else {
  ajustes <- list()
  for (e in names(EXPOSICOES)) {
    cat(sprintf("%s exposição '%s' (%s)...\n", agora(), e, EXPOSICOES[[e]]$nome))
    cbi <- cross_exposicao(b, EXPOSICOES[[e]])
    um <- function(k) {
      r <- tryCatch(ajustar_segmento(Y[[k]], b, cbi, fora, kt), error = function(err) { message("falhou ", k, ": ", conditionMessage(err)); NULL })
      if (!is.null(r)) cat(sprintf("  %s %-52s %s n=%d RR(ref1)=%.3f\n", agora(), k, r$fam, r$n, r$rr[1, 1]))
      r
    }
    res <- if (cores > 1) parallel::mclapply(names(Y), um, mc.cores = cores, mc.preschedule = FALSE) else lapply(names(Y), um)
    res <- lapply(res, function(r) if (inherits(r, "try-error")) NULL else r)      # processo filho que morreu volta como try-error
    names(res) <- names(Y)
    ajustes[[e]] <- res
  }
  falhas <- unique(unlist(lapply(ajustes, function(a) names(a)[vapply(a, is.null, TRUE)])))
  if (length(falhas)) {
    cat("removendo segmentos sem ajuste:", paste(falhas, collapse = "; "), "\n")
    for (e in names(ajustes)) ajustes[[e]] <- ajustes[[e]][setdiff(names(ajustes[[e]]), falhas)]
    Y <- Y[setdiff(names(Y), falhas)]
  }
}
if (!reaproveitou) saveRDS(list(ajustes = ajustes, k_tempo = kt, fim = cx$fim), rds)

cat(agora(), "montando o JSON...\n")
dados <- montar_figura1(cx, Y, ajustes, kt)
tam <- escrever_json(dados, file.path(saida, sprintf("figura1_%s.json", pop)))
escrever_json(resumo_figura1(dados, cx), file.path(saida, sprintf("resumo_%s.json", pop)))
cat(sprintf("%s pronto: %s (%.1f MB), %d segmentos\n", agora(), file.path(saida, sprintf("figura1_%s.json", pop)), tam / 1e6, length(Y)))
