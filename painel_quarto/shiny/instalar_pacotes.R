#!/usr/bin/env Rscript
# Instala os pacotes de R que faltam para o painel Shiny e imprime as versões.
# Rodar como administrador para que o usuário do Shiny Server enxergue os pacotes:
#   sudo Rscript shiny/instalar_pacotes.R
# Se a compilação do nanoparquet falhar por falta de compilador: sudo apt install build-essential

pacotes <- c("shiny", "mgcv", "dlnm", "nanoparquet", "jsonlite", "future", "promises")
faltam <- pacotes[!vapply(pacotes, requireNamespace, TRUE, quietly = TRUE)]
if (length(faltam)) {
  cat("Instalando:", paste(faltam, collapse = ", "), "\n")
  install.packages(faltam, repos = "https://cloud.r-project.org")
}
for (p in pacotes)
  cat(sprintf("%-12s %s\n", p, if (requireNamespace(p, quietly = TRUE)) as.character(utils::packageVersion(p)) else "NÃO INSTALADO"))
if (!all(vapply(pacotes, requireNamespace, TRUE, quietly = TRUE))) quit(save = "no", status = 1L)
