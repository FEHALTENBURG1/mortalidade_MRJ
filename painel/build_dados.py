"""Séries semanais, RR por local x faixa etária e clima diário. Uso: POP=res|todos python build_dados.py"""
import sys, os, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"
cx = nu.contexto(POP); d = cx.d[cx.d.natural]; dias, An, C = cx.dias, cx.A, cx.clima
print(POP, "óbitos naturais", len(d), "| período", dias[0].date(), dias[-1].date(), "| meses fora:", [str(p) for p in cx.ruins], flush=True)
Y = nu.series_local_faixa(d, dias)

# ---------- RR por local x faixa x definição x esquema x recorte
EXPS = {n: nu.exposicoes(C.evento[n]) for n in nu.DEFS}
rows = []
for dn in nu.DEFS:
    for esq, X in EXPS[dn].items():
        for per in nu.PERIODOS:
            m = An.mask[per]
            for (L, fx), y in Y.items():
                if y[m].sum() < 300: continue
                f = nu.ajustar_dia(y, X, An, per)
                rr, lo, hi, p = nu.ic(f["est"], f["se"])
                for j, k in enumerate(X.columns):
                    ex = X[k].to_numpy()[m] > 0
                    rows.append(dict(d=dn, x=esq, s=per, l=L, f=fx, t=k, rr=round(float(rr[j]), 4), lo=round(float(lo[j]), 4), hi=round(float(hi[j]), 4),
                                     p=float(p[j]), n=int(y[m].sum()), dx=int(ex.sum()), ox=int(y[m][ex].sum())))
print(len(rows), "estimativas de RR", flush=True)

# ---------- série semanal e faixa esperada
ini, okw, wk, mw, cov_w, inc_w = nu.grade_semanal(cx)
ev_ab = np.nan_to_num(C.evento[nu.NOME_ABS]); ev_an = np.nan_to_num(C.evento[nu.NOME_ANOM])
nb = pd.Series(ev_ab, index=dias).groupby(ini).sum().reindex(okw).astype(int)
na = pd.Series(ev_an, index=dias).groupby(ini).sum().reindex(okw).astype(int)
cl = C.cl
mxh = cl.hi_max.groupby(ini).max().reindex(okw).round(1); mt = cl.t_med.groupby(ini).mean().reindex(okw).round(1)
S = {}
for (L, fx), y in Y.items():
    yw = pd.Series(y, index=dias).groupby(ini).sum().reindex(okw).to_numpy(float)
    if yw[mw].sum() < 300: continue
    mu, phi = nu.ajuste_semanal(yw, okw, mw); sd = np.sqrt(phi * mu)
    nz = lambda a: [None if np.isnan(v) else round(float(v), 1) for v in a]        # semanas fora do ajuste ficam sem esperado (null)
    S[f"{L}|{fx}"] = dict(o=[int(v) for v in yw], e=nz(mu), l=nz(np.maximum(mu - 1.96 * sd, 0)), u=nz(mu + 1.96 * sd), phi=round(float(phi), 2))
semanas = dict(ini=[x.strftime("%Y-%m-%d") for x in okw], ano=[int(v) for v in wk.ano], se=[int(v) for v in wk.se], nb=[int(v) for v in nb], na=[int(v) for v in na],
               mxh=[None if pd.isna(v) else float(v) for v in mxh], mt=[None if pd.isna(v) else float(v) for v in mt], cov=[bool(v) for v in cov_w], inc=[bool(v) for v in inc_w])

# ---------- clima diário e resumo anual
an = C.an
cd = dict(dia=[x.strftime("%Y-%m-%d") for x in dias], hi_max=[None if pd.isna(v) else round(float(v), 1) for v in cl.hi_max])
cd["nc"] = [None if np.isnan(v) else int(v) for v in nu.nivel_calor(cl)]     # Nível de Calor do protocolo da Prefeitura (1 a 5), reconstruído
for v in ["t_med", "hi_med"]:
    cd[v] = dict(o=[None if pd.isna(x) else round(float(x), 2) for x in an[f"{v}_observado"]], e=[None if pd.isna(x) else round(float(x), 2) for x in an[f"{v}_esperado"]],
                 sd=[None if pd.isna(x) else round(float(x), 2) for x in an[f"{v}_desvio_padrao"]], z=[None if pd.isna(x) else round(float(x), 2) for x in an[f"{v}_z"]])
yr = pd.DataFrame({"ano": dias.year, "ic": ev_ab, "an": ev_an, "ok": ~np.isnan(C.evento[nu.NOME_ABS]), "est": cl.n_estacoes_medio.to_numpy(), "hi": cl.hi_max.to_numpy(), "t": cl.t_med.to_numpy()})
ya = yr.groupby("ano").agg(dias=("ok", "sum"), ic=("ic", "sum"), an=("an", "sum"), est=("est", "mean"), hi=("hi", "mean"), t=("t", "mean")).reset_index()
climaanual = [dict(ano=int(r.ano), dias=int(r.dias), pct_ic=round(100 * r.ic / r.dias, 1), pct_an=round(100 * r.an / r.dias, 1), est=round(float(r.est), 1), hi=round(float(r.hi), 2), t=round(float(r.t), 2)) for r in ya.itertuples()]

dias_ext = {n: int(np.nansum(C.evento[n])) for n in nu.DEFS}
expo = {n: int(np.asarray(EXPS[n]["dia"].iloc[:, 0]).sum()) for n in nu.DEFS}
meta = dict(fim=str(dias[-1].date()), meses_fora=[str(p) for p in cx.ruins], n_dias=len(dias), n_dias_modelo={p: int(An.mask[p].sum()) for p in nu.PERIODOS},
            n_obitos=int(len(d)), dias_expostos_janela=expo)
out = dict(semanas=semanas, series=S, clima=cd, climaanual=climaanual, rr=rows, locais=["Todos os locais"] + nu.LOCAIS, faixas=["Todas as idades"] + nu.FAIXAS, dias_ext=dias_ext, meta=meta)
json.dump(out, open(A_ + f"dados_painel_{POP}.json", "w"), ensure_ascii=False, separators=(",", ":"))
print("ok", os.path.getsize(A_ + f"dados_painel_{POP}.json") / 1e6, "MB;", len(S), "séries;", len(rows), "RR")
