# Funções de dados da Figura 1 (versão em R).
# Lê os óbitos do SIM no data lake (silver, Parquet), aplica as mesmas regras do painel em Python (nucleo.py) e devolve
# as contagens diárias por local do óbito, faixa etária e raça/cor. As faixas etárias são as da UNICEF (0-4, 5-9, 10-19 e décadas depois).

INICIO_SERIE <- as.Date("2006-01-01")          # o SIM do data lake começa em 2006; o clima, em abril de 2007
COVID        <- as.Date(c("2020-03-01", "2022-06-30"))
LIMIAR_MES   <- 0.80                           # mês com taxa diária < 80% da mediana dos 12 meses de referência anteriores = registro não consolidado
MIN_OBITOS   <- 300                            # mínimo de óbitos no ajuste para estimar uma série

LOCAIS <- c("Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais", "Ignorado")
FAIXAS <- c("0-4", "5-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+")
CORTES_IDADE <- c(-Inf, 5, 10, 20, 30, 40, 50, 60, 70, 80, Inf)     # intervalos [a, b): 0-4 vai até 4,99 anos
RACAS  <- c("Branca", "Preta", "Parda", "PPI")                      # PPI = preta + parda + indígena
PPI    <- c("Preta", "Parda", "Indígena")
RACA_SIM <- c("1" = "Branca", "2" = "Preta", "3" = "Amarela", "4" = "Parda", "5" = "Indígena")   # RACACOR do SIM

# ---------------------------------------------------------------- causas
# A causa básica (CAUSABAS do SIM, 3 ou 4 caracteres, sem ponto) classifica cada óbito em exatamente um destes grupos, aplicados nesta ordem:
#   ausente    sem código;
#   invalida   código fora do formato da CID-10 (letra e dois dígitos, mais um dígito opcional) ou de categoria que a CID-10 não tem (por exemplo, D90 ou Y99);
#   covid      B34.2 (código completo de 4 caracteres) e U07 (U07.1 e U07.2); os demais B34 (B34.0, B34.1, B34.8, B34.9...) são infecções virais e não COVID-19;
#   natural    A00 a R99;
#   lesao      S00 a T98 como causa básica (a CID-10 manda codificar a causa básica de uma lesão no capítulo das causas externas; por isso é registro a investigar);
#   externa    V01 a Y98;
#   outros_validos   demais códigos válidos (U00 a U99 que não são COVID-19, e Z00 a Z99).
GRUPOS_CAUSA <- c(natural = "Causas naturais, A00 a R99, exceto COVID-19",
                  covid = "COVID-19 (B34.2 e U07)",
                  externa = "Causas externas, V01 a Y98",
                  lesao = "Lesões e envenenamentos (S00 a T98) como causa básica",
                  outros_validos = "Outros códigos válidos (U00 a U99 exceto COVID-19, e Z00 a Z99)",
                  ausente = "Causa básica ausente",
                  invalida = "Código de CID-10 inválido")

# Faixas de categorias (3 caracteres) que existem na CID-10, por bloco; o que está entre blocos (D90 a D99, E91 a E99, H96 a H99, K94 a K99, P97 a P99, T99, V00, Y99) é inválido.
CID_BLOCOS <- list(c("A00", "B99"), c("C00", "D49"), c("D50", "D89"), c("E00", "E90"), c("F00", "F99"), c("G00", "G99"), c("H00", "H59"), c("H60", "H95"),
                   c("I00", "I99"), c("J00", "J99"), c("K00", "K93"), c("L00", "L99"), c("M00", "M99"), c("N00", "N99"), c("O00", "O99"), c("P00", "P96"),
                   c("Q00", "Q99"), c("R00", "R99"), c("S00", "T98"), c("U00", "U99"), c("V01", "Y98"), c("Z00", "Z99"))

limpar_cid <- function(cid) {                  # maiúsculas, sem espaços nem ponto; vazio vira NA
  x <- gsub(".", "", toupper(trimws(as.character(cid))), fixed = TRUE)
  x[!nzchar(x)] <- NA_character_
  x
}
categoria_cid_valida <- function(cat3) {
  ok <- rep(FALSE, length(cat3))
  for (b in CID_BLOCOS) ok <- ok | (!is.na(cat3) & cat3 >= b[1] & cat3 <= b[2])
  ok
}
eh_covid <- function(cid) {
  x <- limpar_cid(cid)
  !is.na(x) & (x == "B342" | substr(x, 1, 3) == "U07")
}
classificar_causa <- function(cid) {
  x <- limpar_cid(cid)
  g <- rep("outros_validos", length(x))
  letra <- substr(x, 1, 1)
  g[!is.na(x) & letra >= "A" & letra <= "R"] <- "natural"
  g[!is.na(x) & letra %in% c("S", "T")] <- "lesao"
  g[!is.na(x) & letra %in% c("V", "W", "X", "Y")] <- "externa"
  g[eh_covid(x)] <- "covid"
  g[!is.na(x) & !(grepl("^[A-Z][0-9]{2}[0-9]?$", x) & categoria_cid_valida(substr(x, 1, 3)))] <- "invalida"
  g[is.na(x)] <- "ausente"
  factor(g, levels = names(GRUPOS_CAUSA))
}
# Causas naturais: A00 a R99, exceto COVID-19 (B34.2 e U07)
eh_natural <- function(cid) classificar_causa(cid) == "natural"

# Causas de óbito que o filtro do Shiny oferece e os grupos de GRUPOS_CAUSA que cada uma reúne (a Figura 1 em Quarto usa só "naturais").
CAUSAS <- c(naturais = "Causas naturais (CID-10, códigos A00 a R99, exceto COVID-19)", todas_sem_covid = "Todas as causas, exceto COVID-19",
            todas = "Todas as causas, com COVID-19", externas = "Causas externas (CID-10, códigos V01 a Y98)")
CAUSA_GRUPOS <- list(naturais = "natural", todas_sem_covid = setdiff(names(GRUPOS_CAUSA), "covid"), todas = names(GRUPOS_CAUSA), externas = "externa")

# Tabela de reconciliação: contagem de óbitos por grupo de causa e detalhes que explicam a classificação (B34.2 x demais B34, lesões, códigos inválidos).
# A soma dos grupos é o total de óbitos elegíveis (os da população nos dias da análise). d precisa de cid4 (código completo) e grupo.
reconciliar_causas <- function(d) {
  n <- as.integer(table(d$grupo)[names(GRUPOS_CAUSA)])
  g <- data.frame(grupo = names(GRUPOS_CAUSA), rotulo = unname(GRUPOS_CAUSA), n = n, stringsAsFactors = FALSE)
  c4 <- d$cid4
  det <- function(rot, sel) data.frame(rotulo = rot, n = sum(sel, na.rm = TRUE), stringsAsFactors = FALSE)
  detalhe <- rbind(
    det("B34.2 (COVID-19)", c4 %in% "B342"),
    det("Demais B34 (B34.0, B34.1, B34.3 a B34.9), contados nas causas naturais", substr(c4, 1, 3) %in% "B34" & !(c4 %in% "B342")),
    det("U07 (COVID-19)", substr(c4, 1, 3) %in% "U07"),
    det("S00 a T98 na causa básica", d$grupo == "lesao"),
    det("Código com mais de 4 caracteres ou fora do formato", d$grupo == "invalida" & !grepl("^[A-Z][0-9]{2}[0-9]?$", c4)),
    det("Formato válido, mas categoria inexistente na CID-10", d$grupo == "invalida" & grepl("^[A-Z][0-9]{2}[0-9]?$", c4)))
  list(total = nrow(d), grupos = g, detalhe = detalhe,
       opcoes = lapply(CAUSA_GRUPOS, function(gr) sum(g$n[g$grupo %in% gr])))
}

# ---------------------------------------------------------------- dados
cnes7 <- function(x) {                          # código CNES com 7 dígitos (zeros à esquerda restaurados)
  x <- sub("\\.0$", "", trimws(as.character(x)))
  ifelse(is.na(x), NA_character_, paste0(strrep("0", pmax(7 - nchar(x), 0)), x))
}

tabela_cnes <- function(caminho) {
  t <- utils::read.csv(caminho, colClasses = "character", stringsAsFactors = FALSE)
  t$CODESTAB <- cnes7(t$CODESTAB)
  t$tipo <- suppressWarnings(as.numeric(t$tipo))
  t[!duplicated(t$CODESTAB), c("CODESTAB", "tipo")]
}

classificar_raca <- function(r) {                # 1 branca, 2 preta, 3 amarela, 4 parda, 5 indígena; 9 ou vazio = ignorada
  out <- unname(RACA_SIM[substr(trimws(as.character(r)), 1, 1)])
  out[is.na(out)] <- "Ignorada"
  out
}

# Local do óbito: LOCOCOR do SIM refinado pelo tipo do estabelecimento no CNES (hospital x pronto atendimento/UPA). As atribuições
# seguintes sobrescrevem as anteriores, na mesma ordem do painel em Python.
classificar_local <- function(d, tipo_cnes) {
  tipo <- tipo_cnes$tipo[match(d$CODESTAB, tipo_cnes$CODESTAB)]
  l <- as.character(d$LOCOCOR)
  out <- rep("Outros estabelecimentos de saúde", nrow(d))
  out[tipo %in% c(5, 7, 15, 62)] <- "Hospital"
  out[tipo %in% c(20, 21, 73)] <- "UPA / pronto atendimento"
  out[is.na(tipo) & !is.na(l) & l == "1"] <- "Hospital"
  out[!is.na(l) & l == "3"] <- "Domicílio"
  out[!is.na(l) & l == "4"] <- "Via pública"
  out[!is.na(l) & l %in% c("5", "6")] <- "Outros locais"
  out[is.na(l) | l == "9"] <- "Ignorado"
  out
}

faixa_etaria <- function(idade) cut(idade, CORTES_IDADE, labels = FAIXAS, right = FALSE)

# Todos os óbitos ocorridos no MRJ (residentes ou não), todos os anos do silver.
# DTOBITO vem em UTC com hora 00:00; a data é a data em UTC (ler no fuso local do computador deslocaria o dia).
carregar_obitos <- function(silver) {
  fs <- sort(Sys.glob(file.path(silver, "sim/ocorrencia_mrj/ano_arquivo=20*/part-0.parquet")))
  if (!length(fs)) stop("Nenhum arquivo do SIM em ", file.path(silver, "sim/ocorrencia_mrj"))
  cols <- c("DTOBITO", "idade_anos", "CAUSABAS", "LOCOCOR", "CODESTAB", "RACACOR", "ocorrencia_mrj", "residente_mrj")
  d <- do.call(rbind, lapply(fs, function(f) nanoparquet::read_parquet(f, col_select = cols)))
  d <- d[d$ocorrencia_mrj %in% TRUE, ]
  data.frame(
    dia = as.Date(d$DTOBITO, tz = "UTC"),
    idade_anos = as.numeric(d$idade_anos),
    cid = substr(limpar_cid(d$CAUSABAS), 1, 3),        # categoria (3 caracteres), usada na aba de causas específicas
    cid4 = limpar_cid(d$CAUSABAS),                     # código completo, para classificar a causa (B34.2 x demais B34, S a T, inválidos)
    LOCOCOR = as.character(d$LOCOCOR),
    CODESTAB = cnes7(d$CODESTAB),
    residente = d$residente_mrj %in% TRUE,
    raca = classificar_raca(d$RACACOR),
    stringsAsFactors = FALSE)
}

# ---------------------------------------------------------------- registro do SIM
# Meses com registro não consolidado. O mês é marcado se cumprir ao menos uma destas regras, todas definidas a partir do próprio registro do SIM e nunca do resultado do modelo:
#   (a) taxa diária (óbitos / dias com algum óbito registrado) abaixo de LIMIAR x a mediana dos 12 meses de referência anteriores;
#   (b) algum dia do mês, entre o primeiro e o último dia com óbito do arquivo, sem nenhum óbito registrado (arquivo ainda não carregado);
#   (c) mês em que o arquivo termina antes do último dia do mês (último mês do arquivo, incompleto).
# Meses de COVID e meses já marcados não entram na referência da regra (a); mês sem nenhum registro não é marcado aqui (são dias sem registro).
# O ajuste principal retira esses meses (R/modelo_joao.R, COD_PADRAO); a sensibilidade os mantém.
meses_nao_consolidados <- function(dia_obitos, inicio = INICIO_SERIE, limiar = LIMIAR_MES) {
  d <- dia_obitos[dia_obitos >= inicio]
  meses <- seq(as.Date(format(min(d), "%Y-%m-01")), as.Date(format(max(d), "%Y-%m-01")), by = "month")
  chave <- format(meses, "%Y-%m")
  n    <- as.numeric(table(factor(format(d, "%Y-%m"), levels = chave)))
  dreg <- as.numeric(table(factor(format(unique(d), "%Y-%m"), levels = chave)))
  dcal <- as.numeric(table(factor(format(seq(min(d), max(d), by = "day"), "%Y-%m"), levels = chave)))   # dias de calendário de cada mês até o último dia com óbito
  taxa <- ifelse(dreg > 0, n / dreg, NA_real_)
  fim_ult <- seq(as.Date(format(max(d), "%Y-%m-01")), by = "month", length.out = 2)[2] - 1
  pre <- (dreg > 0 & dreg < dcal) | (chave == format(max(d), "%Y-%m") & max(d) < fim_ult)       # regras (b) e (c)
  em_covid <- chave >= format(COVID[1], "%Y-%m") & chave <= format(COVID[2], "%Y-%m")
  boas <- numeric(0); ruim <- pre
  for (i in seq_along(chave)) {
    valido <- !em_covid[i] && !is.na(taxa[i])
    if (valido && !pre[i] && length(boas) >= 12) ruim[i] <- taxa[i] < limiar * stats::median(utils::tail(boas, 12))
    if (valido && !ruim[i]) boas <- c(boas, taxa[i])
  }
  list(meses = meses, ruim = ruim, taxa = taxa)
}

# Período da análise: do início da série até o menor entre o último dia com óbito no SIM e o último dia com clima.
definir_periodo <- function(dia_obitos, ultimo_dia_clima, inicio = INICIO_SERIE) {
  fim <- min(max(dia_obitos), as.Date(ultimo_dia_clima))
  nc <- meses_nao_consolidados(dia_obitos, inicio)
  list(inicio = inicio, fim = fim, meses_nc = nc$meses[nc$ruim & nc$meses <= fim])
}

# Dias sem nenhum óbito (qualquer causa ou residência) no SIM: arquivo ainda não carregado. Não são observações de "zero óbitos".
dias_sem_registro <- function(dia_obitos, dias) !(dias %in% unique(dia_obitos))

# ---------------------------------------------------------------- clima
runs <- function(e, minimo = 2) {                # dias com e == TRUE dentro de uma sequência de pelo menos `minimo` dias seguidos
  r <- rle(as.integer(e)); comp <- rep(r$lengths, r$lengths)
  rep(r$values, r$lengths) == 1L & comp >= minimo
}

# Nível de Calor (NC1 a NC5) do protocolo da Prefeitura do Rio (Decreto Rio nº 54.740/2024), reconstruído do HAAT:
#   a = pelo menos 4 h com índice de calor >= 36 °C; b = pelo menos 4 h >= 40 °C; c = pelo menos 2 h >= 44 °C
#   NC2: a, em sequência de 1 ou 2 dias; NC3: a, em sequência de 3 dias ou mais; NC4: b dentro de uma sequência NC3; NC5: c dentro de uma sequência NC3.
# Usa só o observado e o corte >= (o decreto diz "acima de"). Dia sem clima = NA.
nivel_calor <- function(cl) {
  z <- function(v) ifelse(is.na(v), 0, v)
  a <- z(cl$num_hr_36) >= 4; b <- z(cl$num_hr_40) >= 4; c <- z(cl$num_hr_44) >= 2
  sq <- runs(a, 3); nc <- rep(1, nrow(cl)); nc[a] <- 2; nc[sq] <- 3; nc[sq & b] <- 4; nc[sq & c] <- 5
  nc[is.na(cl$num_hr_36)] <- NA
  nc
}

carregar_clima <- function(caminho) {
  cl <- utils::read.csv(caminho, stringsAsFactors = FALSE)
  cl$dia <- as.Date(cl$dia)
  cl[order(cl$dia), ]
}

# ---------------------------------------------------------------- semanas epidemiológicas (domingo a sábado)
semanas <- function(dias) {
  wd <- as.POSIXlt(dias)$wday
  ini <- dias - wd
  quarta <- ini + 3
  n <- table(factor(as.character(ini)))
  ok <- names(n)[n == 7]
  ini_ok <- as.Date(ok)
  q <- ini_ok + 3
  list(ini = ini, ini_ok = ini_ok, ano = as.integer(format(q, "%Y")), se = as.POSIXlt(q)$yday %/% 7 + 1L)
}

# ---------------------------------------------------------------- séries diárias
serie_dias <- function(dias_do_obito, dias) tabulate(match(as.integer(dias_do_obito), as.integer(dias)), nbins = length(dias))

# Contagens diárias por segmento. Chaves "local|faixa" e "local|Todas as idades|raça" (mesmo formato do painel em Python).
# Local: "Todos os locais" mais os sete locais. Faixa: "Todas as idades" mais as faixas da UNICEF. Raça/cor (todas as idades): Branca, Preta, Parda e PPI.
series_segmentos <- function(d, dias) {
  Y <- list()
  for (L in c("Todos os locais", LOCAIS)) {
    dl <- if (L == "Todos os locais") d else d[d$local == L, ]
    Y[[paste0(L, "|Todas as idades")]] <- serie_dias(dl$dia, dias)
    for (fx in FAIXAS) Y[[paste0(L, "|", fx)]] <- serie_dias(dl$dia[dl$faixa %in% fx], dias)
    for (r in RACAS) {
      sel <- if (r == "PPI") dl$raca %in% PPI else dl$raca == r
      Y[[paste0(L, "|Todas as idades|", r)]] <- serie_dias(dl$dia[sel], dias)
    }
  }
  Y
}

# ---------------------------------------------------------------- causas de óbito no cache do Shiny
COLUNAS_SERIE <- c("dia", "idade_anos", "raca", "local", "faixa")      # o que series_segmentos() e a tabela de raça/cor usam

# Versão do contexto que vai para o cache: mantém os óbitos naturais em cx$d e guarda os de outras causas, só com as colunas necessárias, em cx$d_extra
# (com a marca covid e a causa básica). Descarta as tabelas que o painel não usa.
enxugar_contexto <- function(cx) {
  d <- cx$d_todas_causas
  if (!is.null(d)) {
    ex <- d[!d$natural, c(COLUNAS_SERIE, "cid", "grupo")]              # a causa básica (3 caracteres) e o grupo de causa ficam, para a aba de causas específicas
    ex$covid <- ex$grupo == "covid"
    rownames(ex) <- NULL
    cx$d_extra <- ex
  }
  cx$d_todas_causas <- NULL; cx$cl_completo <- NULL
  cx
}

# Óbitos de uma causa (ver CAUSAS) a partir de um contexto enxuto (cx$d naturais + cx$d_extra).
obitos_causa <- function(cx, causa) {
  stopifnot(causa %in% names(CAUSAS))
  nat <- cx$d[, COLUNAS_SERIE]
  if (causa == "naturais") return(nat)
  if (is.null(cx$d_extra)) stop("o cache não traz as causas não naturais: rode shiny/atualizar_cache.R --forcar")
  ex <- cx$d_extra
  switch(causa,
         externas = ex[ex$grupo == "externa", COLUNAS_SERIE],
         todas_sem_covid = rbind(nat, ex[!ex$covid, COLUNAS_SERIE]),
         todas = rbind(nat, ex[, COLUNAS_SERIE]))
}

# ---------------------------------------------------------------- contexto completo
# pop = "res" (residentes que morreram no Rio) ou "todos" (todos os óbitos ocorridos no Rio)
contexto <- function(silver, clima_csv, cnes_csv, pop = "res", inicio = INICIO_SERIE) {
  d_all <- carregar_obitos(silver)
  cl <- carregar_clima(clima_csv)
  per <- definir_periodo(d_all$dia, max(cl$dia[!is.na(cl$hi_max)]), inicio)
  dias <- seq(per$inicio, per$fim, by = "day")
  d <- d_all[d_all$dia >= per$inicio & d_all$dia <= per$fim, ]
  if (pop == "res") d <- d[d$residente, ]
  d$grupo <- classificar_causa(d$cid4)
  d$natural <- d$grupo == "natural"
  d$local <- classificar_local(d, tabela_cnes(cnes_csv))
  d$faixa <- faixa_etaria(d$idade_anos)
  dn <- d[d$natural, ]
  sr <- dias_sem_registro(d_all$dia, dias)
  nc_mes <- format(dias, "%Y-%m") %in% format(per$meses_nc, "%Y-%m")
  list(pop = pop, d = dn, d_todas_causas = d, reconc = reconciliar_causas(d), dias = dias, fim = per$fim, inicio = per$inicio, meses_nc = per$meses_nc,
       sem_registro = sr, nao_consolidado = nc_mes & !sr, covid = dias >= COVID[1] & dias <= COVID[2],
       clima = cbind(dia = dias, cl[match(dias, cl$dia), setdiff(names(cl), "dia")]), cl_completo = cl)
}
