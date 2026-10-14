"""RR por janela de anos: reestima o modelo inteiro em cada janela [início, fim] (anos civis completos) e guarda as tabelas que o painel lê.

O painel não calcula nada no navegador: a escolha de "De / Até" só seleciona uma das janelas calculadas aqui.
Cada janela refaz o ajuste do zero (spline de tempo com 7 gl por ano de dados da janela, dia da semana, erro-padrão robusto HAC),
com as mesmas regras do período completo: COVID fora do ajuste no recorte "Sem COVID", meses incompletos e dias sem clima fora.

Custo: cada ajuste leva ~0,03 s. Figuras 2, 3 e 3b (RR e defasagens) são baratas. Horas x limiar e CIDs somam milhares de ajustes por janela;
a grade "completa" (padrão) as calcula em todas as janelas (cerca de uma hora de CPU por população; o workflow usa todos os núcleos) e a "reduzida"
só nas janelas que começam no primeiro ano ou terminam no último.

Uso: POP=res|todos python janelas.py [--pesada completa|reduzida] [--proc N] [--so 2012-2026,2015-2026]
Saídas em analise/: jan_grade_{pop}.csv, jan_rr_{pop}.csv.gz, jan_lag_{pop}.csv.gz, jan_heat_{pop}.csv.gz, jan_cid_{pop}.csv.gz
"""
import sys, os, argparse, time, warnings, multiprocessing as mp
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu

POP = os.environ.get("POP", "res"); A_ = "analise/"
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--pesada", choices=["reduzida", "completa"], default="completa")
ap.add_argument("--proc", type=int, default=os.cpu_count() or 1)
ap.add_argument("--so", default="", help="lista de janelas AAAA-AAAA separadas por vírgula (teste)")
ARGS = ap.parse_args()

MIN_CID = 1500          # mesma regra de cid.py, agora contada dentro da janela
NL = 8                  # defasagens 0 a 7 (como defasagem.py)
LIM = list(range(32, 45)); HORAS = [1, 2, 3, 4, 6, 8, 10, 12]
LOCS = ["Todos os locais", "Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais"]

cx = nu.contexto(POP); d = cx.d; dias, An, C = cx.dias, cx.A, cx.clima
Y = nu.series_local_faixa(d[d.natural], dias)
EXPS = {n: nu.exposicoes(C.evento[n]) for n in nu.DEFS}
LAGX = {}
for dn in nu.DEFS:
    ev = C.evento[dn]
    LAGX[dn] = (pd.DataFrame({f"lag{k}": pd.Series(np.nan_to_num(ev)).shift(k).fillna(0).to_numpy() for k in range(NL)}),
                pd.Series(np.isnan(ev).astype(float)).rolling(NL, min_periods=1).max().to_numpy() > 0)

# pivôs diários por causa (só causas que podem chegar a MIN_CID em alguma janela), uma vez para todas as janelas
dc = d[~d.covid]
PIV = {}
for L in LOCS:
    dl = dc if L == "Todos os locais" else dc[dc.local == L]
    for fxn, dd in ([("Todas as idades", dl), ("61+", dl[dl.idade_anos >= 61])] if L == "Todos os locais" else [("Todas as idades", dl)]):
        cnt = dd.cid.value_counts(); cids = cnt[cnt >= MIN_CID].index.tolist()
        PIV[(L, fxn)] = dd.groupby(["dia", "cid"]).size().unstack(fill_value=0).reindex(dias, fill_value=0)[cids] if cids else None


def f4(v): return round(float(v), 4)


def tarefa(w):
    y0, y1, pesada = w; t0 = time.time()
    rr_, lag_, heat_, cid_ = [], [], [], []
    for per in nu.PERIODOS:
        m = An.mascara(per, y0, y1)
        if m.sum() < nu.MIN_DIAS_JANELA: continue
        # ---- Figuras 2 e 3: RR por local x faixa x definição x esquema
        for dn in nu.DEFS:
            for esq, X in EXPS[dn].items():
                for (L, fx), y in Y.items():
                    if y[m].sum() < 300: continue
                    f = nu.ajustar_dia(y, X, An, per, mask=m)
                    rr, lo, hi, p = nu.ic(f["est"], f["se"])
                    for j, k in enumerate(X.columns):
                        ex = X[k].to_numpy()[m] > 0
                        rr_.append((dn, esq, per, L, fx, k, f4(rr[j]), f4(lo[j]), f4(hi[j]), float(p[j]), int(y[m].sum()), int(ex.sum()), int(y[m][ex].sum())))
        # ---- Figura 3b: defasagens 0-7 e acumulados
        for dn in nu.DEFS:
            XL, nan = LAGX[dn]; mm = m & ~nan
            if mm.sum() < nu.MIN_DIAS_JANELA: continue
            p_ = nu.controles_diarios(dias, mm, An.df_ano)[0].shape[1]
            cum = lambda a, b: np.r_[np.zeros(a), np.ones(b - a + 1), np.zeros(NL - b - 1 + p_)]
            cont = np.vstack([np.r_[np.eye(NL)[k], np.zeros(p_)] for k in range(NL)] + [cum(0, 1), cum(0, 3), cum(0, NL - 1)])
            nomes = [f"lag{k}" for k in range(NL)] + ["cum01", "cum03", "cum07"]
            for (L, fx), y in Y.items():
                if y[mm].sum() < 1000: continue
                f = nu.ajustar_dia(y, XL, An, per, mask=mm, contrastes=cont)
                rr, lo, hi, p = nu.ic(f["est"], f["se"])
                for j, nm_ in enumerate(nomes): lag_.append((L, fx, per, dn, nm_, f4(rr[j]), f4(lo[j]), f4(hi[j]), int(y[mm].sum())))
    # ---- partes pesadas: só no recorte "Sem COVID" (padrão) e só nas janelas da grade pesada
    m = An.mascara("Sem COVID", y0, y1)
    if pesada and m.sum() >= nu.MIN_DIAS_JANELA:
        per = "Sem COVID"
        for k in LIM:                                                     # Figura 1b: horas x limiar
            nh = C.cl[f"num_hr_{k}"].to_numpy(float)
            for h in HORAS:
                e = nu.janela_max(np.nan_to_num(nh) >= h).astype(float); nd = int(e[m].sum())
                if nd < nu.MIN_DIAS_EXPOSTOS or nd > m.sum() - 30: continue
                X = pd.DataFrame({"x": e})
                for (L, fx), y in Y.items():
                    if y[m].sum() < 300: continue
                    f = nu.ajustar_dia(y, X, An, per, mask=m)
                    rr, lo, hi, p = nu.ic(f["est"], f["se"])
                    heat_.append((L, fx, per, k, h, f4(rr[0]), f4(lo[0]), f4(hi[0]), int(y[m].sum()), nd))
        jan = np.asarray((dias >= f"{y0}-01-01") & (dias <= f"{y1}-12-31"))
        for (L, fxn), piv in PIV.items():                                 # Figura 4: causas básicas, FDR dentro da janela
            if piv is None: continue
            cnt = piv[jan].sum(); cids = cnt[cnt >= MIN_CID].index.tolist()
            for c in cids:
                y = piv[c].to_numpy(float)
                for dn in nu.DEFS:
                    for esq, X in EXPS[dn].items():
                        f = nu.ajustar_dia(y, X, An, per, mask=m)
                        rr, lo, hi, p = nu.ic(f["est"], f["se"])
                        for j, k in enumerate(X.columns):
                            ex = X[k].to_numpy()[m] > 0
                            cid_.append((fxn, L, c, per, dn, esq, k, f4(rr[j]), f4(lo[j]), f4(hi[j]), float(p[j]), int(y[m].sum()), int(ex.sum()), int(y[m][ex].sum())))
    return (y0, y1, rr_, lag_, heat_, cid_, round(time.time() - t0, 1))


def pesada_ok(y0, y1, a0, a1):
    return ARGS.pesada == "completa" or y0 == a0 or y1 == a1


if __name__ == "__main__":
    a0, a1 = int(dias[0].year), int(dias[-1].year)
    grade = An.janelas()
    if ARGS.so:
        quer = {tuple(int(v) for v in s.split("-")) for s in ARGS.so.split(",")}
        grade = [g for g in grade if (g["y0"], g["y1"]) in quer]
    tarefas = [(g["y0"], g["y1"], pesada_ok(g["y0"], g["y1"], a0, a1)) for g in grade]
    tarefas.sort(key=lambda t: (not t[2], -(t[1] - t[0])))               # janelas pesadas e longas primeiro (melhor balanceamento)
    print(f"{POP}: {len(tarefas)} janelas ({sum(t[2] for t in tarefas)} com horas e CID) | {ARGS.proc} processos", flush=True)
    t0 = time.time(); res = []
    with mp.get_context("fork").Pool(ARGS.proc) as pool:
        for i, r in enumerate(pool.imap_unordered(tarefa, tarefas, chunksize=1), 1):
            res.append(r); print(f"  {i}/{len(tarefas)} janela {r[0]}-{r[1]} em {r[6]} s | {(time.time() - t0) / 60:.1f} min", flush=True)
    res.sort(key=lambda r: (r[0], r[1]))
    def tab(i, cols, extra):
        rows = [(r[0], r[1], *x) for r in res for x in r[i]]
        return pd.DataFrame(rows, columns=["y0", "y1", *cols])
    R = tab(2, "d x s l f t rr lo hi p n dx ox".split(), None); R.to_csv(A_ + f"jan_rr_{POP}.csv.gz", index=False)
    Lg = tab(3, "l f s d t rr lo hi n".split(), None); Lg.to_csv(A_ + f"jan_lag_{POP}.csv.gz", index=False)
    Hm = tab(4, "l f s limiar horas rr lo hi n dx".split(), None); Hm.to_csv(A_ + f"jan_heat_{POP}.csv.gz", index=False)
    Cd = tab(5, "faixa l c s d x t rr lo hi p n dx ox".split(), None)
    if len(Cd):
        Cd["q"] = Cd.groupby(["y0", "y1", "l", "faixa", "s", "d", "x", "t"]).p.transform(lambda s: nu.bh(s.to_numpy())).round(5)
        Cd["a"] = Cd.c.map(nu.eh_natural); Cd["i"] = Cd.c.map(nu.influenciado)
    Cd.to_csv(A_ + f"jan_cid_{POP}.csv.gz", index=False)
    G = pd.DataFrame([dict(y0=g["y0"], y1=g["y1"], dias_sem_covid=g["dias"]["Sem COVID"], dias_todo=g["dias"]["Todo o período"],
                           pesada=bool(pesada_ok(g["y0"], g["y1"], a0, a1)) and g["dias"]["Sem COVID"] >= nu.MIN_DIAS_JANELA) for g in An.janelas()])
    G.to_csv(A_ + f"jan_grade_{POP}.csv", index=False)
    print(f"{POP}: janelas {len(G)} | RR {len(R)} | defasagem {len(Lg)} | horas {len(Hm)} | CID {len(Cd)} linhas | {(time.time() - t0) / 60:.1f} min")
