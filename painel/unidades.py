"""RR por unidade de saúde e por bairro (do estabelecimento) e dados da janela de datas do mapa. Uso: POP=res|todos python unidades.py"""
import sys, os, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
POP = os.environ.get("POP", "res"); A_ = "analise/"
MIN_UNID, MIN_BAIRRO, MIN_ANOS, MIN_COBERTURA, APARA = 1500, 3000, 4.0, 0.90, 90
cx = nu.contexto(POP); d = cx.d[cx.d.natural]; dias, An, C = cx.dias, cx.A, cx.clima
det = nu.tabela_cnes(A_ + "cnes_estab_det.csv"); det = det[det.erro.isna()].set_index("CODESTAB")
for c in ("lat", "lon"): det[c] = pd.to_numeric(det[c], errors="coerce")
du = d[d.local.isin(["Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde"]) & d.CODESTAB.notna()].copy()
du["tem"] = du.CODESTAB.isin(det.index)
cob = dict(obitos_em_unidades=int(len(du)), com_cnes=int(du.tem.sum()), com_coord=int(du.CODESTAB.map(det.lat).notna().sum()))
du = du[du.tem].copy(); du["bairro"] = du.CODESTAB.map(det.bairro)
du["tipoloc"] = du.CODESTAB.map(det.tipo).map(lambda t: "UPA / pronto atendimento" if t in (20, 21, 73) else "Hospital" if t in (5, 7, 15, 62) else "Outros estabelecimentos de saúde")
EXP = {n: nu.exposicoes(C.evento[n])["dia"].iloc[:, 0].to_numpy() for n in nu.DEFS}
base = An.mask["Sem COVID"]
IDX = {n: [int(i) for i in np.where((EXP[n] > 0) & base)[0]] for n in nu.DEFS}
meses = pd.period_range(dias[0], dias[-1], freq="M")

def janela_atividade(y):
    """Intervalo em que a unidade está em operação (primeiro a último óbito, aparado em APARA dias nas pontas para não modelar a abertura/fechamento).
    Devolve (máscara de dias, cobertura mensal) ou None se a série não é estável."""
    nz = np.where(y > 0)[0]
    if len(nz) == 0: return None
    a, b = nz[0], nz[-1]
    if a > 0: a += APARA          # abriu depois do início do período
    if b < len(y) - 1: b -= APARA  # fechou antes do fim
    if (b - a) / 365.25 < MIN_ANOS: return None
    m = np.zeros(len(y), bool); m[a:b + 1] = True
    mm = pd.Series(y[m], index=dias[m]).groupby(dias[m].to_period("M")).sum()
    cobm = float((mm > 0).mean())
    return (m, cobm) if cobm >= MIN_COBERTURA else None

def ajusta(y, m):
    out = {}
    for n in nu.DEFS:
        X = pd.DataFrame({"x": EXP[n]})
        try:
            f = nu.ajustar_dia(y, X, An, "Sem COVID", mask=m)
        except Exception:
            out[n] = None; continue
        rr, lo, hi, p = nu.ic(f["est"], f["se"]); out[n] = [round(float(rr[0]), 4), round(float(lo[0]), 4), round(float(hi[0]), 4)]
        out[n].append(f)
    return out

unid, uj, estaveis = [], {}, set()
for c, g in du.groupby("CODESTAB"):
    n = len(g); row = det.loc[c]
    it = dict(c=c, nome=str(row.nome), bairro=str(row.bairro), lat=None if pd.isna(row.lat) else float(row.lat), lon=None if pd.isna(row.lon) else float(row.lon),
              tp=g.tipoloc.iloc[0], n=n, rr=None, ativo=None, motivo=None)
    if n >= MIN_UNID:
        y = nu.serie_dias(g, dias); ja = janela_atividade(y)
        if ja is None:
            it["motivo"] = "série instável (abriu/fechou no período ou com meses sem óbitos)"
        else:
            m_u, cobm = ja; m = base & m_u
            if y[m].sum() >= MIN_UNID:
                fits = ajusta(y, m); it["rr"] = {k: v[:3] for k, v in fits.items() if v}
                a = np.where(m_u)[0]; it["ativo"] = [str(dias[a[0]].date()), str(dias[a[-1]].date())]; it["n_modelo"] = int(y[m].sum()); estaveis.add(c)
                un = {}
                for k, v in fits.items():
                    if not v: continue
                    f = v[3]; X = pd.DataFrame({"x": EXP[k]}); mu_all = np.zeros(len(dias))
                    # esperado sem exposição nos dias expostos da janela: mu / RR (equivale a prever com x = 0)
                    C_ = nu.controles_diarios(dias, m, An.df_ano)[0]; Xfull = np.column_stack([np.zeros(m.sum()), C_]); mu0 = np.exp(Xfull @ f["b"])
                    mu_all[m] = mu0
                    ix = np.array(IDX[k]); ok = m[ix]
                    un[k] = dict(o=[int(y[i]) if m[i] else 0 for i in ix], m=[round(float(mu_all[i]), 3) if m[i] else 0 for i in ix], phi=round(max(f["phi"], 1.0), 3))
                uj[c] = un
            else:
                it["motivo"] = "menos de 1.500 óbitos na janela de atividade"
    unid.append(it)

bair = []
for b, g in du.groupby("bairro"):
    n = len(g); it = dict(b=b, n=n, hosp=int((g.tipoloc == "Hospital").sum()), upa=int((g.tipoloc == "UPA / pronto atendimento").sum()),
                          out=int((g.tipoloc == "Outros estabelecimentos de saúde").sum()), nu=int(g.CODESTAB.nunique()), rr=None, n_rr=0)
    ge = g[g.CODESTAB.isin(estaveis)]
    if n >= MIN_BAIRRO and len(ge) >= MIN_BAIRRO:
        y = nu.serie_dias(ge, dias); fits = ajusta(y, base); it["rr"] = {k: v[:3] for k, v in fits.items() if v}; it["n_rr"] = int(len(ge))
    bair.append(it)
print(POP, "unidades", len(unid), "com RR", sum(1 for u in unid if u["rr"]), "| bairros", len(bair), "com RR", sum(1 for b in bair if b["rr"]), cob, flush=True)
json.dump(dict(unidades=unid, bairros=bair, cobertura=cob, uj=dict(dias=[x.strftime("%Y-%m-%d") for x in dias], idx=IDX, u=uj), criterios=dict(min_unid=MIN_UNID, min_bairro=MIN_BAIRRO, min_anos=MIN_ANOS, min_cobertura=MIN_COBERTURA, apara=APARA)),
          open(A_ + f"unidades_{POP}.json", "w"), ensure_ascii=False, separators=(",", ":"))
print("ok", os.path.getsize(A_ + f"unidades_{POP}.json") / 1e6, "MB")
