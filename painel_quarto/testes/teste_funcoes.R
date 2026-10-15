# Testes das funções de dados (sem precisar do data lake). Uso: Rscript testes/teste_funcoes.R (a partir da pasta do projeto)
# Os rótulos têm acento: garante locale UTF-8 antes de ler o resto do script (em sessões com locale "C" os literais seriam lidos como bytes soltos)
if (!l10n_info()[["UTF-8"]]) suppressWarnings(try(Sys.setlocale("LC_ALL", "C.UTF-8"), silent = TRUE))
raiz <- if (file.exists("R/funcoes.R")) "." else ".."
source(file.path(raiz, "R/utf8.R")); fonte_utf8(file.path(raiz, "R/funcoes.R"))
ok <- function(cond, msg) { if (!isTRUE(cond)) stop("FALHOU: ", msg, call. = FALSE); cat("ok  ", msg, "\n") }

# --- causas
ok(identical(eh_natural(c("I219", "J189", "R99", "V892", "X954", "B342", "U071", "C509", "", NA, "A15")), c(TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, TRUE)), "causas naturais: A a R, sem V a Y e sem COVID (B34 e U)")
ok(all(eh_covid(c("B34", "B342", "U07")) & !eh_covid(c("B33", "I10", NA))), "COVID: B34 e códigos U")

# --- faixas etárias da UNICEF: limites inferiores incluídos
idade <- c(0, 0.5, 4.99, 5, 9, 10, 19.9, 20, 29, 30, 79.9, 80, 105, NA)
esp <- c("0-4", "0-4", "0-4", "5-9", "5-9", "10-19", "10-19", "20-29", "20-29", "30-39", "70-79", "80+", "80+", NA)
ok(identical(as.character(faixa_etaria(idade)), esp), "faixas da UNICEF (0-4, 5-9, 10-19, décadas, 80+)")
ok(identical(FAIXAS, c("0-4", "5-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+")), "10 faixas")

# --- raça/cor
ok(identical(classificar_raca(c("1", "2", "3", "4", "5", "9", NA, "")), c("Branca", "Preta", "Amarela", "Parda", "Indígena", "Ignorada", "Ignorada", "Ignorada")), "RACACOR do SIM")

# --- CNES com 7 dígitos
ok(identical(cnes7(c("49", "2269988", "0000063.0", NA)), c("0000049", "2269988", "0000063", NA)), "CNES com zeros à esquerda")

# --- local do óbito
tipo <- data.frame(CODESTAB = c("0000001", "0000002", "0000003", "0000004"), tipo = c(5, 20, 1, NA))
d <- data.frame(CODESTAB = c("0000001", "0000002", "0000003", "0000004", "0000004", NA, "0000001", NA, NA),
                LOCOCOR  = c("1", "1", "1", "1", "2", "3", "3", "4", NA), stringsAsFactors = FALSE)
esp <- c("Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Hospital", "Outros estabelecimentos de saúde", "Domicílio", "Domicílio", "Via pública", "Ignorado")
ok(identical(classificar_local(d, tipo), esp), "local: tipo CNES refina LOCOCOR; domicílio e via pública prevalecem")

# --- data do óbito: o parquet guarda 00:00 UTC; ler no fuso local deslocaria o dia
x <- as.POSIXct("2015-02-11 00:00:00", tz = "UTC")
Sys.setenv(TZ = "America/Sao_Paulo")
ok(as.character(as.Date(x, tz = "UTC")) == "2015-02-11", "DTOBITO: data em UTC, independente do fuso do computador")

# --- registro não consolidado: 14 meses normais (10 óbitos/dia), depois um mês com 6 por dia (60%) e um com 9 por dia (90%)
set.seed(1)
dias <- seq(as.Date("2010-01-01"), as.Date("2011-06-30"), by = "day")
taxa <- ifelse(format(dias, "%Y-%m") == "2011-03", 6, ifelse(format(dias, "%Y-%m") == "2011-05", 9, 10))
dia_obitos <- rep(dias, taxa)
r <- meses_nao_consolidados(dia_obitos, as.Date("2010-01-01"))
ruim <- format(r$meses[r$ruim], "%Y-%m")
ok(identical(ruim, "2011-03"), "mês a 60% da referência é marcado; mês a 90% não é")
# a taxa usa os dias com registro: mês em que só os 10 primeiros dias foram carregados não é marcado
dia_obitos2 <- c(dia_obitos[dia_obitos < as.Date("2011-06-01")], rep(seq(as.Date("2011-06-01"), as.Date("2011-06-10"), by = "day"), 10))
r2 <- meses_nao_consolidados(dia_obitos2, as.Date("2010-01-01"))
ok(!"2011-06" %in% format(r2$meses[r2$ruim], "%Y-%m"), "mês com poucos dias carregados mas taxa normal não é marcado")
ok(all(dias_sem_registro(dia_obitos2, seq(as.Date("2011-06-08"), as.Date("2011-06-12"), by = "day")) == c(FALSE, FALSE, FALSE, TRUE, TRUE)), "dias sem nenhum óbito = sem registro")
per <- definir_periodo(dia_obitos2, as.Date("2011-06-30"), as.Date("2010-01-01"))
ok(per$fim == as.Date("2011-06-10"), "fim = menor entre o último dia com óbito e o último dia com clima")

# --- nível de calor (protocolo): 3 dias seguidos com >= 4 h a 36 °C viram NC3; com >= 4 h a 40 °C, NC4; com >= 2 h a 44 °C, NC5
cl <- data.frame(num_hr_36 = c(0, 5, 0, 6, 7, 8, 9, 5, 5, 5, NA), num_hr_40 = c(0, 0, 0, 0, 0, 4, 0, 0, 0, 0, NA), num_hr_44 = c(0, 0, 0, 0, 0, 0, 0, 0, 0, 2, NA))
ok(identical(nivel_calor(cl), c(1, 2, 1, 3, 3, 4, 3, 3, 3, 5, NA)), "NC1 a NC5 do protocolo, NA sem clima")

# --- semanas epidemiológicas (domingo a sábado); 2006-01-01 foi domingo
s <- semanas(seq(as.Date("2006-01-01"), as.Date("2006-01-20"), by = "day"))
ok(length(s$ini_ok) == 2 && s$ini_ok[1] == as.Date("2006-01-01") && s$se[1] == 1L, "semanas completas de domingo a sábado")

# --- séries diárias
dd <- seq(as.Date("2020-01-01"), as.Date("2020-01-05"), by = "day")
ok(identical(serie_dias(as.Date(c("2020-01-02", "2020-01-02", "2020-01-05", "2019-12-31")), dd), c(0L, 2L, 0L, 0L, 1L)), "contagem diária ignora datas fora do período")
cat("\nTodos os testes passaram.\n")
