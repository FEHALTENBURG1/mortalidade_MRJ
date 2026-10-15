# Le um arquivo .R em UTF-8 e avalia no ambiente global, marcando as strings como UTF-8 (so ASCII neste arquivo).
# Necessario porque source() em sessoes com locale "C" (containers, CI) estraga rotulos com acento (Domicilio, Via publica...).
fonte_utf8 <- function(arquivo) {
  linhas <- readLines(arquivo, encoding = "UTF-8", warn = FALSE)
  for (e in parse(text = linhas, keep.source = FALSE, encoding = "UTF-8")) eval(e, globalenv())
  invisible(NULL)
}
