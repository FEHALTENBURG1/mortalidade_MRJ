"""Figura 1 (óbitos x esperado) desde 2006: séries semanal e diária para cada local x faixa etária. Uso: POP=res|todos python serie1.py
Saída: analise/serie1_{pop}.json. O SIM do data lake começa em 2006 e o clima em abril de 2007; os modelos de RR das demais abas seguem em 2012 (nucleo.INICIO).

Semanal: esperado de quase-Poisson com spline de tempo (7 gl por ano), sem exposição, ajustado nas semanas fora de COVID e de mês incompleto.
Diário: para cada definição de dia de calor (índice de calor máx. >= 36 °C, anomalia térmica z >= 1,96, ou NC2 a NC5 do protocolo) um modelo com o calor em t, t-1, t-2
e t-3 (janela de 4 dias, como nos RR); o esperado é o contrafactual com o calor zerado. Dias sem dado de clima (antes de 17/04/2007; anomalia antes de 2012) entram
no ajuste como dia sem calor. Cada combinação de local e faixa etária tem seu próprio modelo e sua dispersão φ.
Mesmas combinações da série semanal original (mínimo de 300 óbitos).
Raça/cor (RACACOR do SIM): além de local x faixa etária, há local x raça/cor (Branca, Preta, Parda e o agregado PPI = preta + parda + indígena; todas as idades), com o
mesmo método. Indígena tem óbitos de menos para uma série própria e entra só no PPI; amarela e os óbitos sem cor entram só na série "Todas"."""
import sys, os, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"
cx = nu.contexto(POP, inicio=nu.INICIO_SERIE, clima="heat/data/temp_df_longo.csv"); d = cx.d[cx.d.natural]; dias, An, C = cx.dias, cx.A, cx.clima
print(POP, "óbitos naturais", len(d), "| de", dias[0].date(), "a", dias[-1].date(), "| meses fora:", [str(p) for p in cx.ruins], flush=True)
Y = nu.series_local_faixa(d, dias)
Y.update(nu.series_local_raca(d, dias))                                   # local x raça/cor (todas as idades): chave 'local|Todas as idades|raça'
RC = d.raca.value_counts()
assert RC.sum() == len(d)
assert int(Y[("Todos os locais", "Todas as idades|PPI")].sum()) == int(RC.reindex(nu.PPI).fillna(0).sum()), "PPI não soma preta + parda + indígena"
assert all(int(Y[("Todos os locais", f"Todas as idades|{r}")].sum()) == int(RC.get(r, 0)) for r in ("Branca", "Preta", "Parda")), "séries por raça não somam"
print("raça/cor (óbitos naturais, série inteira):", RC.to_dict(), flush=True)
cl = C.cl
hi = cl.hi_max.to_numpy(float); z = C.an["t_med_z"].to_numpy(float); nc = nu.nivel_calor(cl)
EV = {"ic": (hi >= nu.LIM_HI), "an": (z >= nu.LIM_Z), "nc": (np.nan_to_num(nc) >= 2)}          # NaN (sem clima) conta como dia sem calor
EV = {k: v.astype(float) for k, v in EV.items()}
XW = {k: nu.janela_max(v).astype(float) for k, v in EV.items()}                                  # exposto = calor em t, t-1, t-2 ou t-3
ok_clima = ~np.isnan(hi)
m_fit = ~(An.inc | An.covid)                                                                     # o clima não restringe o ajuste desta figura

# ---------- semanal
ini, okw, wk = nu.semanas(dias)
cov_w = pd.Series(An.covid, index=dias).groupby(ini).any().reindex(okw).to_numpy()
inc_w = pd.Series(An.inc, index=dias).groupby(ini).any().reindex(okw).to_numpy()
mw = ~(cov_w | inc_w)
nb = pd.Series(EV["ic"], index=dias).groupby(ini).sum().reindex(okw).astype(int)
na = pd.Series(EV["an"], index=dias).groupby(ini).sum().reindex(okw).astype(int)
mxh = cl.hi_max.groupby(ini).max().reindex(okw).round(1); mt = cl.t_med.groupby(ini).mean().reindex(okw).round(1)
ncl = pd.Series(ok_clima, index=dias).groupby(ini).sum().reindex(okw)
nn = lambda s: [None if pd.isna(v) else float(v) for v in s]
sem = dict(ini=[x.strftime("%Y-%m-%d") for x in okw], ano=[int(v) for v in wk.ano], se=[int(v) for v in wk.se], nb=[int(v) for v in nb], na=[int(v) for v in na],
           mxh=nn(mxh), mt=nn(mt), cov=[bool(v) for v in cov_w], inc=[bool(v) for v in inc_w], cl=[bool(v >= 4) for v in ncl])
S, K, O, E, F, R = {}, [], [], {k: [] for k in EV}, {k: [] for k in EV}, {k: [] for k in EV}
nz = lambda a: [None if np.isnan(v) else round(float(v), 1) for v in a]
for (L, fx), y in Y.items():
    yw = pd.Series(y, index=dias).groupby(ini).sum().reindex(okw).to_numpy(float)
    if yw[mw].sum() < 300: continue                                                              # mesma regra da série semanal original
    mu, phi = nu.ajuste_semanal(yw, okw, mw); sd = np.sqrt(phi * mu)
    S[f"{L}|{fx}"] = dict(o=[int(v) for v in yw], e=nz(mu), l=nz(np.maximum(mu - 1.96 * sd, 0)), u=nz(mu + 1.96 * sd), phi=round(float(phi), 2))
    # ---------- diário: um modelo por definição de calor
    K.append(f"{L}|{fx}"); O.append([int(v) for v in y])
    for k in EV:
        f = nu.ajuste_diario(y, An, X=XW[k], mask=m_fit)
        E[k].append([None if np.isnan(v) else int(round(float(v) * 10)) for v in f["mu"]]); F[k].append(round(f["phi"], 2))
        R[k].append([round(f["rr"], 4), round(f["lo"], 4), round(f["hi"], 4)])
cl_ = dict(hi_max=[None if np.isnan(v) else round(float(v), 1) for v in hi],
           hi_med=[None if pd.isna(v) else round(float(v), 2) for v in cl.hi_med], t_med=[None if pd.isna(v) else round(float(v), 2) for v in cl.t_med],
           nc=[None if np.isnan(v) else int(v) for v in nc])
out = dict(rc={k: int(v) for k, v in RC.items()}, dias=[x.strftime("%Y-%m-%d") for x in dias], cl=cl_, sem=sem, S=S, k=K, o=O, e=E, f=F, r=R,
           x={k: [int(v) for v in XW[k]] for k in XW}, ev={k: [int(v) for v in EV[k]] for k in EV},
           inc=[int(v) for v in An.inc], cov=[int(v) for v in An.covid], ok=[int(v) for v in ok_clima])
json.dump(out, open(A_ + f"serie1_{POP}.json", "w"), separators=(",", ":"))
print(POP, len(K), "séries |", len(dias), "dias |", len(okw), "semanas |", round(os.path.getsize(A_ + f"serie1_{POP}.json") / 1e6, 2), "MB (JSON)")
