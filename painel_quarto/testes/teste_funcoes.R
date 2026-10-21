# Testes das funções de dados (sem precisar do data lake). Uso: Rscript testes/teste_funcoes.R (a partir da pasta do projeto)
# Os rótulos têm acento: garante locale UTF-8 antes de ler o resto do script (em sessões com locale "C" os literais seriam lidos como bytes soltos)
if (!l10n_info()[["UTF-8"]]) suppressWarnings(try(Sys.setlocale("LC_ALL", "C.UTF-8"), silent = TRUE))
raiz <- if (file.exists("R/funcoes.R")) "." else ".."
source(file.path(raiz, "R/utf8.R")); fonte_utf8(file.path(raiz, "R/funcoes.R"))
ok <- function(cond, msg) { if (!isTRUE(cond)) stop("FALHOU: ", msg, call. = FALSE); cat("ok  ", msg, "\n") }

# --- causas
ok(identical(eh_natural(c("I219", "J189", "R99", "V892", "X954", "B342", "U071", "C509", "", NA, "A15", "B349", "B34", "S720", "Z000")),
             c(TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, TRUE, TRUE, TRUE, FALSE, FALSE)), "causas naturais: A00 a R99, sem COVID-19 (B34.2 e U07); os demais B34 são naturais")
ok(identical(eh_covid(c("B342", "B34.2", "U071", "U072", "U07", "B34", "B349", "B340", "B33", "I10", "U04", NA)), c(TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE)),
   "COVID-19: B34.2 e U07; B34 sem subcategoria ou outras subcategorias de B34 não contam")
cid <- c("I219", "B342", "B349", "U071", "U04", "S720", "T140", "V892", "X954", "Y349", "Z000", "", NA, "R99", "D90", "Y99", "V00", "I2", "ABCDE", "i21.9", "H96", "D49", "K94", "P96", "T98", "T99")
esp <- c("natural", "covid", "natural", "covid", "outros_validos", "lesao", "lesao", "externa", "externa", "externa", "outros_validos", "ausente", "ausente", "natural", "invalida", "invalida", "invalida",
         "invalida", "invalida", "natural", "invalida", "natural", "invalida", "natural", "lesao", "invalida")
ok(identical(as.character(classificar_causa(cid)), esp), "classificação da causa básica: naturais, COVID-19, externas V01 a Y98, lesões S a T, outros válidos, ausentes e inválidos")
ok(identical(levels(classificar_causa(cid)), names(GRUPOS_CAUSA)), "grupos de causa na ordem de GRUPOS_CAUSA")
# reconciliação: a soma dos grupos é o total, e cada opção do seletor soma os grupos que reúne
dr <- data.frame(cid4 = limpar_cid(cid), stringsAsFactors = FALSE); dr$grupo <- classificar_causa(dr$cid4)
rc <- reconciliar_causas(dr)
ok(rc$total == length(cid) && sum(rc$grupos$n) == rc$total, "reconciliação: a soma dos grupos coincide com o total de óbitos elegíveis")
ok(rc$opcoes$todas == rc$total && rc$opcoes$naturais + rc$opcoes$externas + sum(rc$grupos$n[rc$grupos$grupo %in% c("covid", "lesao", "outros_validos", "ausente", "invalida")]) == rc$total &&
   rc$opcoes$todas_sem_covid == rc$total - rc$grupos$n[rc$grupos$grupo == "covid"], "reconciliação: opções do seletor (naturais, externas, todas sem COVID-19, todas)")
ok(rc$detalhe$n[1] == 1 && rc$detalhe$n[2] == 1 && rc$detalhe$n[3] == 1, "reconciliação: detalhe de B34.2, demais B34 e U07")

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
ok("2011-06" %in% format(r2$meses[r2$ruim], "%Y-%m"), "último mês do arquivo incompleto (termina antes do fim do mês) é marcado, mesmo com taxa normal")
dia_obitos3 <- dia_obitos[!(dia_obitos >= as.Date("2010-08-10") & dia_obitos <= as.Date("2010-08-12"))]       # três dias sem nenhum óbito no meio de um mês
r3 <- meses_nao_consolidados(dia_obitos3, as.Date("2010-01-01"))
ok(identical(format(r3$meses[r3$ruim], "%Y-%m"), c("2010-08", "2011-03")), "mês com dia sem nenhum óbito registrado é marcado")
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
