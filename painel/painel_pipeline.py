#!/usr/bin/env python3
"""
Recalcula as tabelas do painel (mortalidade x calor) a partir dos Releases do projeto.

Entradas
  --silver   pasta com silver/sim/ocorrencia_mrj/ano_arquivo=AAAA/part-0.parquet  (Release sim-mrj, silver_sim_mrj.tar.gz)
  --haat     haat_diario_municipal.csv                                           (Release clima-mrj)
  --aux      dados_auxiliares/ (cnes_estab.csv, cnes_estab_det.csv, contorno_rio_simpl.json, cid_nomes.json)
  --silver-sha256   (opcional) hash do arquivo silver_sim_mrj.tar.gz, registrado na aba Métodos
Saídas
  --saida    pasta com meta.json e as tabelas lidas pelo app Shiny (a publicar no Release painel-mrj)
  trabalho/analise/painel_calor_mrj.html   painel HTML autocontido (a publicar no GitHub Pages)

O fim da janela é calculado (nucleo.definir_periodo): último mês completo do SIM e, no máximo, o último dia com clima.
Meses incompletos no meio da série não cortam o período; ficam fora do ajuste.

Figura 1: serie1.py calcula a mortalidade semanal e diária desde 2006 (esperado sem calor, com lag de 0 a 3 dias); os modelos de RR seguem em nucleo.INICIO.
Período da análise: janelas.py reestima o modelo em cada janela de anos civis (De / Até do painel); o HTML só escolhe entre elas.
"""
from __future__ import annotations
import argparse, glob, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import nucleo as nu

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def preparar(a):
    w = Path(a.trabalho); w.mkdir(parents=True, exist_ok=True)
    (w / "silver_user").mkdir(exist_ok=True)
    alvo = w / "silver_user" / "silver"
    if alvo.exists() or alvo.is_symlink(): (alvo.unlink() if alvo.is_symlink() else shutil.rmtree(alvo))
    os.symlink(Path(a.silver).resolve(), alvo)
    h = pd.read_csv(a.haat, parse_dates=["dia"]).sort_values("dia")
    d = nu.carregar_obitos(alvo)
    fim, ruins, _ = nu.definir_periodo(d, h.loc[h.hi_max.notna(), "dia"].max())
    print(f"janela {nu.INICIO} a {fim.date()} | meses incompletos fora do ajuste: {[str(p) for p in ruins]}", flush=True)
    (w / "heat/data").mkdir(parents=True, exist_ok=True)
    h[(h.dia >= nu.INICIO) & (h.dia <= fim)].to_csv(w / "heat/data/temp_df.csv", index=False)
    h[h.dia <= fim].to_csv(w / "heat/data/temp_df_longo.csv", index=False)       # clima desde o início do arquivo (2007): só a Figura 1 (serie1.py) usa; a anomalia e os RR seguem em INICIO
    (w / "analise").mkdir(exist_ok=True)
    for f in ("cnes_estab.csv", "cnes_estab_det.csv", "contorno_rio_simpl.json"): shutil.copy(Path(a.aux) / f, w / "analise" / f)
    shutil.copy(Path(a.aux) / "cid_nomes.json", w / "cid_nomes.json")
    for s in list(AQUI.glob("*.py")) + [AQUI / "painel_template.html"]: shutil.copy(s, w / s.name)
    json.dump(dict(haat_sha256=sha256(a.haat), silver_sha256=a.silver_sha256 or None, silver_arquivos=len(glob.glob(str(Path(a.silver) / "sim/ocorrencia_mrj/ano_arquivo=*/part-0.parquet")))),
              open(w / "meta_fontes.json", "w"))
    return w

ENV1 = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}

def rodar(cmd, w, env=None, log=None):
    e = {**os.environ, **ENV1, **(env or {})}
    return subprocess.Popen([sys.executable, "-I", *cmd], cwd=w, env=e, stdout=open(w / log, "w") if log else None, stderr=subprocess.STDOUT)

def esperar(ps):
    for p in ps:
        if p.wait() != 0: sys.exit(f"falha em {p.args}")

def faixa(w, pop):
    """Uma faixa por população (2 CPUs): os scripts de cada população rodam em sequência."""
    cmds = ["build_dados.py", "serie1.py", "unidades.py", "defasagem.py", "cid.py", "heatmap_horas.py"]
    return subprocess.Popen(["sh", "-c", " && ".join(f"POP={pop} {sys.executable} -I {c} > log_{pop}_{c[:-3]}.txt 2>&1" for c in cmds)], cwd=w, env={**os.environ, **ENV1})

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--silver", required=True); ap.add_argument("--haat", required=True); ap.add_argument("--aux", required=True)
    ap.add_argument("--saida", default="painel_dados"); ap.add_argument("--trabalho", default="trabalho_painel"); ap.add_argument("--silver-sha256", default="")
    ap.add_argument("--pesada", choices=["completa", "reduzida"], default="completa", help="grade de janelas de anos para horas x limiar e CID (ver janelas.py)")
    ap.add_argument("--sem-janelas", action="store_true", help="pula as janelas de anos (teste rápido); o painel fica só com a série inteira")
    ap.add_argument("--proc", type=int, default=os.cpu_count() or 1, help="processos do cálculo por janela")
    a = ap.parse_args()
    w = preparar(a)
    esperar([rodar(["anomalia_haat.py"], w, log="anomalia.log")])
    ps = [faixa(w, p) for p in ("res", "todos")]
    for p in ps:
        if p.wait() != 0: sys.exit("falha em uma das faixas de cálculo (ver log_*.txt em " + str(w) + ")")
    if not a.sem_janelas:                                   # janelas de anos: cada população usa todos os núcleos, uma depois da outra
        for pop in ("res", "todos"):
            esperar([rodar(["janelas.py", "--pesada", a.pesada, "--proc", str(a.proc)], w, env={"POP": pop}, log=f"log_{pop}_janelas.txt")])
    esperar([rodar(["sensibilidade.py"], w, log="sens.log")])
    esperar([rodar(["merge_html.py"], w, log="merge.log")])
    esperar([rodar(["exportar_painel.py", str(Path(a.saida).resolve())], w, log="exportar.log")])
    print("tabelas em", a.saida, "| HTML em", w / "analise/painel_calor_mrj.html")

if __name__ == "__main__":
    main()
