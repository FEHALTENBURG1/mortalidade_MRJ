"""RR de óbito em dias com >= H horas de índice de calor >= K (janela lag 0-3), por local, faixa etária e recorte. Uso: POP=res|todos python heatmap_horas.py"""
import sys, os, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"
cx = nu.contexto(POP); d = cx.d[cx.d.natural]; dias, An, C = cx.dias, cx.A, cx.clima
Y = nu.series_local_faixa(d, dias)
LIM = list(range(32, 45)); HORAS = [1, 2, 3, 4, 6, 8, 10, 12]
rows = []
for per in nu.PERIODOS:
    m = An.mask[per]
    for k in LIM:
        nh = C.cl[f"num_hr_{k}"].to_numpy(float); print(POP, per, "limiar", k, flush=True)
        for h in HORAS:
            e = nu.janela_max(np.nan_to_num(nh) >= h).astype(float)
            nd = int(e[m].sum())
            if nd < nu.MIN_DIAS_EXPOSTOS or nd > m.sum() - 30: continue
            X = pd.DataFrame({"x": e})
            for (L, fx), y in Y.items():
                if y[m].sum() < 300: continue
                f = nu.ajustar_dia(y, X, An, per)
                rr, lo, hi, p = nu.ic(f["est"], f["se"])
                rows.append((POP, L, fx, per, k, h, round(float(rr[0]), 4), round(float(lo[0]), 4), round(float(hi[0]), 4), int(y[m].sum()), nd))
R = pd.DataFrame(rows, columns="pop local faixa periodo limiar horas rr lo hi n dias_expostos".split())
R.to_csv(A_ + f"heatmap_horas_{POP}.csv", index=False); print(POP, len(R), "linhas")
