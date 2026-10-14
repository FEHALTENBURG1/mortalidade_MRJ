"""RR por defasagem (lag 0 a 7, ajustados entre si) e efeito acumulado. Uso: POP=res|todos python defasagem.py"""
import sys, os, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"; NL = 8
cx = nu.contexto(POP); d = cx.d[cx.d.natural]; dias, An, C = cx.dias, cx.A, cx.clima
Y = nu.series_local_faixa(d, dias)
rows = []
for dn in nu.DEFS:
    ev = C.evento[dn]; nan = pd.Series(np.isnan(ev).astype(float)).rolling(NL, min_periods=1).max().to_numpy() > 0
    X = pd.DataFrame({f"lag{k}": pd.Series(np.nan_to_num(ev)).shift(k).fillna(0).to_numpy() for k in range(NL)})
    K = np.vstack([np.eye(NL + 0)[:NL]])                      # contrastes: cada defasagem
    for per in nu.PERIODOS:
        m = An.mask[per] & ~nan
        p_ = nu.controles_diarios(dias, m, An.df_ano)[0].shape[1]
        cum = lambda a, b: np.r_[np.zeros(a), np.ones(b - a + 1), np.zeros(NL - b - 1 + p_)]
        cont = np.vstack([np.r_[np.eye(NL)[k], np.zeros(p_)] for k in range(NL)] + [cum(0, 1), cum(0, 3), cum(0, NL - 1)])
        nomes = [f"lag{k}" for k in range(NL)] + ["cum01", "cum03", "cum07"]
        for (L, fx), y in Y.items():
            if y[m].sum() < 1000: continue
            f = nu.ajustar_dia(y, X, An, per, mask=m, contrastes=cont)
            rr, lo, hi, p = nu.ic(f["est"], f["se"])
            for j, nm_ in enumerate(nomes):
                rows.append((POP, L, fx, per, dn, nm_, round(float(rr[j]), 4), round(float(lo[j]), 4), round(float(hi[j]), 4), int(y[m].sum())))
R = pd.DataFrame(rows, columns="pop local faixa periodo definicao termo rr lo hi n".split())
R.to_csv(A_ + f"defasagem_{POP}.csv", index=False); print(POP, len(R), "linhas")
