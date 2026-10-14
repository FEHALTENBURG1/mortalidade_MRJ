"""RR por causa básica (CID-10, 3 caracteres) em dias de calor, com FDR de Benjamini-Hochberg, por local do óbito e faixa etária,
e série semanal esperada por causa. Todas as causas (naturais e externas), exceto COVID-19 (B34 / códigos U).
Uso: POP=res|todos python cid.py"""
import sys, os, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"; MIN = 1500
cx = nu.contexto(POP); d = cx.d[~cx.d.covid]; dias, An, C = cx.dias, cx.A, cx.clima
ini, okw, wk, mw, cov_w, inc_w = nu.grade_semanal(cx)
EXPS = {n: nu.exposicoes(C.evento[n]) for n in nu.DEFS}
LOCS = ["Todos os locais", "Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais"]
rows, weekly = [], {}
for L in LOCS:
    dl = d if L == "Todos os locais" else d[d.local == L]
    for fxn, dd in ([("Todas as idades", dl), ("61+", dl[dl.idade_anos >= 61])] if L == "Todos os locais" else [("Todas as idades", dl)]):
        cnt = dd.cid.value_counts(); cids = cnt[cnt >= MIN].index.tolist()
        print(POP, L, fxn, len(cids), "CIDs", flush=True)
        if not cids: continue
        piv = dd.groupby(["dia", "cid"]).size().unstack(fill_value=0).reindex(dias, fill_value=0)
        for c in cids:
            y = piv[c].to_numpy(float)
            if fxn == "Todas as idades":
                yw = pd.Series(y, index=dias).groupby(ini).sum().reindex(okw).to_numpy(float)
                mu, phi = nu.ajuste_semanal(yw, okw, mw)
                weekly[f"{c}|{L}"] = dict(o=[int(v) for v in yw], e=[None if np.isnan(v) else round(float(v), 1) for v in mu], phi=round(float(phi), 2))
            for per in nu.PERIODOS:
                m = An.mask[per]
                for dn in nu.DEFS:
                    for esq, X in EXPS[dn].items():
                        f = nu.ajustar_dia(y, X, An, per)
                        rr, lo, hi, p = nu.ic(f["est"], f["se"])
                        for j, k in enumerate(X.columns):
                            ex = X[k].to_numpy()[m] > 0
                            rows.append(dict(pop=POP, faixa=fxn, l=L, cid=c, sens=per, definicao=dn, esquema=esq, termo=k, rr=float(rr[j]), lo=float(lo[j]), hi=float(hi[j]), p=float(p[j]),
                                             n=int(y[m].sum()), dx=int(ex.sum()), obs_exp=int(y[m][ex].sum())))
R = pd.DataFrame(rows)
R["q"] = R.groupby(["l", "faixa", "sens", "definicao", "esquema", "termo"]).p.transform(lambda s: nu.bh(s.to_numpy()))
R["natural"] = R.cid.map(nu.eh_natural); R["sensivel"] = R.cid.map(nu.influenciado)
R.to_csv(A_ + f"cid_rr_{POP}.csv", index=False)
json.dump(weekly, open(A_ + f"cid_semanal_{POP}.json", "w"), separators=(",", ":"))
print(POP, len(R), "linhas; q<0,05:", int((R.q < .05).sum()), len(weekly), "séries semanais", os.path.getsize(A_ + f"cid_semanal_{POP}.json") / 1e6, "MB")
