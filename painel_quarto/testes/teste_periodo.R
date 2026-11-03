#!/usr/bin/env Rscript
# Testa o período de análise (R/servico.R: periodo_valido, fora_periodo, kt_pedido e o parâmetro `per` dos pedidos) com dados simulados, sem rede e sem cache real.
# O período tira do ajuste os dias de fora dele; o modelo é reajustado só com os de dentro.
#
# Uso, a partir da pasta do projeto:   Rscript testes/teste_periodo.R
invisible(try(suppressWarnings(Sys.setlocale("LC_ALL", "C.UTF-8")), silent = TRUE))
raiz <- local({ a <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)); if (length(a)) dirname(dirname(normalizePath(a[1]))) else getwd() })
source(file.path(raiz, "R", "utf8.R"))
for (f in c("funcoes.R", "modelo_joao.R", "exportar.R", "fontes_remotas.R", "servico.R")) fonte_utf8(file.path(raiz, "R", f))

falhas <- character(0)
checar <- function(nome, cond, detalhe = "") {
  ok <- isTRUE(cond); cat(sprintf("%s %s%s\n", if (ok) "ok    " else "FALHOU", nome, if (!ok && nzchar(detalhe)) paste0(" | ", detalhe) else ""))
  if (!ok) falhas <<- c(falhas, nome)
}
cod_erro <- function(expr) tryCatch({ expr; NA_character_ }, error = function(e) sub(":.*$", "", conditionMessage(e)))
json_de <- function(x) jsonlite::fromJSON(json_utf8(x), simplifyVector = FALSE)

# ---------------------------------------------------------------- dados simulados (8 anos, efeito do calor conhecido)
set.seed(11)
dias <- seq(as.Date("2010-01-01"), as.Date("2017-12-31"), by = "day"); n <- length(dias)
doy <- as.POSIXlt(dias)$yday
h <- pmax(0, round(rnorm(n, 5 * pmax(0, cos(2 * pi * (doy - 20) / 365.25)) - 1.5, 2.5)))
clima <- data.frame(dia = dias, hi_max = 30 + h, hi_med = 28, t_med = 25, auc36 = 0.5 * h^1.2)
for (K in LIMIARES) clima[[paste0("num_hr_", K)]] <- pmin(24, pmax(0, round(h + (36 - K) * 0.7)))
lag3 <- sapply(0:3, function(l) c(rep(0, l), h[seq_len(n - l)]))
mu <- exp(log(80) + 0.15 * cos(2 * pi * (doy - 20) / 365.25) + 0.004 * rowSums(lag3))
tot <- rnbinom(n, mu = mu, size = 80)
N <- sum(tot)
d <- data.frame(dia = rep(dias, tot), stringsAsFactors = FALSE)
d$local <- sample(LOCAIS, N, TRUE, prob = c(.45, .1, .05, .25, .1, .0496, .0004 * 10))
d$faixa <- sample(FAIXAS, N, TRUE, prob = c(.02, .01, .02, .04, .06, .1, .15, .2, .2, .2))
d$raca <- sample(c("Branca", "Preta", "Parda", "Amarela", "Indígena"), N, TRUE, prob = c(.5, .15, .3, .03, .02))
d$idade_anos <- 50
d$cid <- sample(c("I21", "I10", "J18", "C34", "E11", "R99"), N, TRUE, prob = c(.3, .25, .2, .1, .1, .05))
covid <- rep(FALSE, n); covid[dias >= as.Date("2012-12-15") & dias <= as.Date("2013-03-15")] <- TRUE      # período curto de "COVID" simulado, para o caso de poucos dias no ajuste
cx <- list(pop = "res", d = d, d_extra = NULL, dias = dias, inicio = dias[1], fim = dias[n], meses_nc = as.Date(character(0)),
           sem_registro = rep(FALSE, n), nao_consolidado = rep(FALSE, n), covid = covid, clima = clima)
pasta <- tempfile("cache_periodo_"); dir.create(pasta)
chave <- "teste0000001"
saveRDS(list(cx = cx, meta = list(chave = chave, pop = "res")), file.path(pasta, sprintf("contexto_res_%s.rds", chave)))
jsonlite::write_json(list(chave = chave, pop = "res"), caminho_meta(pasta, "res"), auto_unbox = TRUE)
P <- obter_P(pasta, "res", chave)
checar("cache simulado lido", !is.null(P))

# ---------------------------------------------------------------- texto do período
checar("período válido: 'todos' e anos inteiros", all(vapply(c("todos", "2010-2017", "2012-2013", "2010-2011"), periodo_valido, TRUE)))
checar("período inválido: malformado, de um ano só, invertido ou fora do texto", !any(vapply(c("2012", "2012-2012", "2015-2012", "12-2015", "2012-15", "2012-2015 ", "todos ", "", "Todos", "2012/2015", "20122015"), periodo_valido, TRUE)))
checar("período inválido: NA, número, vetor", !periodo_valido(NA_character_) && !periodo_valido(2012) && !periodo_valido(c("2010-2012", "2010-2013")))
checar("período fora dos anos da série não vale com o contexto", !periodo_valido("2005-2012", cx) && !periodo_valido("2012-2020", cx) && periodo_valido("2010-2017", cx))

# ---------------------------------------------------------------- dias fora e spline de tempo
fp <- fora_periodo(cx, "2012-2015")
checar("dias fora do período: os de fora de 2012 a 2015", sum(!fp) == sum(as.integer(format(dias, "%Y")) %in% 2012:2015) && all(format(dias[!fp], "%Y") %in% 2012:2015))
checar("'todos' não tira dia nenhum", !any(fora_periodo(cx, "todos")))
checar("fora_pedido soma as retiradas e o período", identical(fora_pedido(cx, "100", "2012-2015"), fora_ajuste(cx, opc_de_codigo("100")) | fp) || identical(fora_pedido(cx, "100", "2012-2015"), (cx$sem_registro | cx$covid) | fp))
checar("base do spline de tempo: série inteira = P$kt; período de 4 anos = proporcional (mínimo 6)", identical(kt_pedido(P, "todos"), P$kt) && kt_pedido(P, "2012-2015") == max(round(12 * sum(!fp) / (12.5 * 365.25)), 6) && P$kt > kt_pedido(P, "2012-2015"),
       sprintf("kt todos = %d, kt 2012-2015 = %d", P$kt, kt_pedido(P, "2012-2015")))

# ---------------------------------------------------------------- ajuste com período
K1 <- "Todos os locais|Todas as idades"
r_todos <- executar_ajuste(pasta, "res", chave, K1, "horas")
r_per <- executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2012-2015")
pt <- json_de(r_todos$payload); pp <- json_de(r_per$payload)
num <- function(x) as.numeric(unlist(lapply(x, function(v) if (is.null(v)) NA_real_ else v)))
checar("payload traz o período e a base do spline", identical(pp$per, "2012-2015") && identical(pt$per, "todos") && pp$kt == kt_pedido(P, "2012-2015") && pt$kt == P$kt)
e_dia <- num(pp$e)
dentro <- !fp
checar("esperado diário só existe dentro do período", all(is.na(e_dia[fp])) && !anyNA(e_dia[dentro]))
checar("a série inteira tem esperado em todos os dias", !anyNA(num(pt$e)))
se <- num(pp$S$e); sem <- semanas(dias); g <- factor(as.character(sem$ini), levels = as.character(sem$ini_ok))
semana_dentro <- as.logical(tapply(!fp, g, all))
checar("esperado semanal: NA nas semanas com algum dia fora do período, número nas demais", identical(is.na(se), !semana_dentro))
checar("o observado diário e o semanal não mudam com o período", identical(num(pp$o), num(pt$o)) && identical(num(pp$So), num(pt$So)))
checar("o RR do período difere do RR da série inteira (outro ajuste)", !isTRUE(all.equal(num(pp$rr), num(pt$rr))), sprintf("todos %.4f, período %.4f", num(pt$rr)[1], num(pp$rr)[1]))
checar("o IC do período é mais largo que o da série inteira (menos dados)", (num(pp$rr)[3] - num(pp$rr)[2]) > (num(pt$rr)[3] - num(pt$rr)[2]))
checar("curvas de exposição-resposta acompanham o período", !is.null(pp$cv) && length(pp$cv$x) == 41)

# cache em disco: o período entra no nome do arquivo e na conferência
f1 <- arquivo_ajuste(pasta, chave, "res", "horas", K1); f2 <- arquivo_ajuste(pasta, chave, "res", "horas", K1, "naturais", "000", "2012-2015")
checar("períodos diferentes usam arquivos diferentes", f1 != f2 && file.exists(f1) && file.exists(f2))
r2 <- executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2012-2015")
checar("2ª chamada do mesmo período vem do disco e é igual", r2$do_cache && identical(json_de(r2$payload), pp))
checar("o ajuste guardado de um período não é lido como de outro", is.null(ler_ajuste(pasta, chave, "res", "horas", K1, "naturais", "000", "2013-2016")) && !is.null(ler_ajuste(pasta, chave, "res", "horas", K1, "naturais", "000", "2012-2015")))
x <- readRDS(f2); x$per <- "2011-2014"; saveRDS(x, f2)
checar("arquivo com outro período gravado dentro (colisão ou adulteração) é refeito", is.null(ler_ajuste(pasta, chave, "res", "horas", K1, "naturais", "000", "2012-2015")))

# erros
checar("período malformado: erro recorte_invalido", all(vapply(c("2012", "2012-2012", "2015-2012", "x", "2012-2015;"), function(p) identical(cod_erro(executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", p)), "recorte_invalido"), TRUE)))
checar("período fora da série: erro recorte_invalido", identical(cod_erro(executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2005-2012")), "recorte_invalido") &&
       identical(cod_erro(executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2012-2022")), "recorte_invalido"))
msg <- tryCatch(executar_ajuste(pasta, "res", chave, "Ignorado|Todas as idades", "horas", "naturais", "000", "2012-2013"), error = function(e) conditionMessage(e))
checar("recorte com óbitos suficientes na série e insuficientes no período: erro recorte_invalido com a mensagem do período", grepl("^recorte_invalido", msg) && grepl("período escolhido", msg), msg)
checar("o mesmo recorte na série inteira tem óbitos suficientes", !is.null(executar_ajuste(pasta, "res", chave, "Ignorado|Todas as idades", "horas")$payload))

# período que só toca o início da "COVID" (17 dias < MIN_DIAS_COVID): o termo do período sai do modelo e o ajuste sai
r_cv <- tryCatch(executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2010-2012"), error = function(e) conditionMessage(e))
checar("período que toca poucos dias de COVID: ajusta sem o termo do período", is.list(r_cv) && !is.null(r_cv$payload), if (is.character(r_cv)) r_cv else "")
r_cv2 <- tryCatch(executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "000", "2011-2014"), error = function(e) conditionMessage(e))
checar("período que contém o 'COVID' inteiro: ajusta com o termo", is.list(r_cv2) && !is.null(r_cv2$payload), if (is.character(r_cv2)) r_cv2 else "")

# a retirada de COVID e o período valem juntos
r_cov <- executar_ajuste(pasta, "res", chave, K1, "horas", "naturais", "100", "2011-2014")
e_cov <- num(json_de(r_cov$payload)$e)
checar("retirada de COVID + período: sem esperado fora do período nem no 'COVID'", all(is.na(e_cov[fora_pedido(cx, "100", "2011-2014")])) && !anyNA(e_cov[!fora_pedido(cx, "100", "2011-2014")]))

# mapa, causas específicas e série por causa respeitam o período
rm1 <- executar_ajuste(pasta, "res", chave, K1, "mapa36", "naturais", "000", "2012-2015")
pm <- json_de(rm1$payload); pm0 <- json_de(executar_ajuste(pasta, "res", chave, K1, "mapa36")$payload)
checar("mapa: coluna do período traz o período e menos dias expostos", identical(pm$per, "2012-2015") && sum(num(pm$nd), na.rm = TRUE) < sum(num(pm0$nd), na.rm = TRUE))
lc <- json_de(executar_ajuste(pasta, "res", chave, K1, "cidlista", "naturais", "000", "2012-2015")$payload); lc0 <- json_de(executar_ajuste(pasta, "res", chave, K1, "cidlista")$payload)
checar("lista de causas: contagens do período menores que as da série inteira", identical(lc$per, "2012-2015") && length(lc$cid) > 0 && all(num(lc$n) < num(lc0$n[match(unlist(lc$cid), unlist(lc0$cid))])))
rc <- json_de(executar_ajuste(pasta, "res", chave, K1, "cid_I21_horas", "naturais", "000", "2012-2015")$payload)
checar("causa específica: RR, IC e p do período, com a base do spline do período", identical(rc$per, "2012-2015") && length(rc$rr) == 2 && rc$kt == kt_pedido(P, "2012-2015") && all(num(rc$lo) < num(rc$rr)) && all(num(rc$p) >= 0))
rs <- json_de(executar_ajuste(pasta, "res", chave, K1, "cidsem_I21_horas", "naturais", "000", "2012-2015")$payload)
checar("série semanal da causa: esperado só nas semanas do período", identical(is.na(num(rs$S$e)), !semana_dentro))

cat(sprintf("\n%s\n", if (length(falhas)) paste("FALHARAM:", paste(falhas, collapse = "; ")) else "Todos os testes do período passaram."))
quit(save = "no", status = if (length(falhas)) 1L else 0L)
