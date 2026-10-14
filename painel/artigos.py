"""Análises dos artigos sobre o local do óbito: o risco de morrer em dias de calor muda conforme o lugar onde a pessoa morreu?

Reaproveita o núcleo do painel (nucleo.py): mesmo desfecho (óbitos diários do SIM, residentes do Rio de Janeiro), mesma exposição (dia de calor em
t, t-1, t-2 ou t-3), mesmo modelo (Poisson de quase-verossimilhança, spline de tempo com 7 gl por ano, dia da semana, EP robusto HAC com 14 defasagens),
mesmo recorte ("Sem COVID", 2012 em diante). O que este script acrescenta é o CONTRASTE entre locais: razão de RR = exp(beta_a - beta_b) com
IC e p calculados sobre a série de influência combinada (nu.combinar), que trata os dois locais como medidas dos mesmos dias.

Uso (na pasta de trabalho do pipeline, depois de painel_pipeline.py):  python artigos.py [parte ...]
partes: desc locais lag defs sens idade cap capx cv   (sem argumento, todas). Saída em analise/artigos/*.csv
"""
import sys, os, json, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, statsmodels.api as sm, nucleo as nu

OUT = "analise/artigos/"; os.makedirs(OUT, exist_ok=True)
PARTES = sys.argv[1:] or ["desc", "locais", "lag", "defs", "sens", "idade", "cap", "capx", "cv"]
T0 = time.time()
def log(*a): print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)

# ---------------------------------------------------------------- dados
cx = nu.contexto("res"); ct = nu.contexto("todos")
dias, A, C = cx.dias, cx.A, cx.clima
M0 = A.mask["Sem COVID"]
D = {"res": cx.d[cx.d.natural].copy(), "todos": ct.d[ct.d.natural].copy()}          # causas naturais, sem COVID-19
for k in D:
    D[k]["cap"] = D[k].cid.str[0]
    D[k]["idade61"] = np.where(D[k].idade_anos.isna(), "ign", np.where(D[k].idade_anos >= 61, "61+", "<61"))   # idade ignorada fora de 61+ e de <61
    D[k]["banda"] = pd.cut(D[k].idade_anos, [-np.inf, 21, 31, 41, 51, 61, 71, 81, np.inf], right=False,
                           labels=["0–20", "21–30", "31–40", "41–50", "51–60", "61–70", "71–80", "81+"])
log("dados:", {k: len(v) for k, v in D.items()}, "dias no ajuste", int(M0.sum()))

LOCS = {"Hospital": "Hospital", "UPA": "UPA / pronto atendimento", "Domicílio": "Domicílio",
        "Outros estab.": "Outros estabelecimentos de saúde", "Outros locais": "Outros locais", "Via pública": "Via pública"}
def serie(df, loc):
    return nu.serie_dias(df if loc == "Todos" else df[df.local == LOCS[loc]], dias)

# ---------------------------------------------------------------- exposições
EV = {"ic": C.evento[nu.NOME_ABS], "an": C.evento[nu.NOME_ANOM]}
NC = nu.nivel_calor(C.cl)
for k in (2, 3, 4, 5): EV[f"nc{k}"] = np.where(np.isnan(NC), np.nan, (NC >= k).astype(float))
NOMES_DEF = {"ic": "Calor intenso (IC máx. ≥ 36 °C)", "an": "Anomalia térmica (z ≥ 1,96)", "nc2": "Nível de Calor ≥ 2", "nc3": "Nível de Calor ≥ 3",
             "nc4": "Nível de Calor ≥ 4", "nc5": "Nível de Calor 5"}
EXPO = {k: nu.exposicoes(v) for k, v in EV.items()}
XIC = EXPO["ic"]["dia"]

def aj(y, X, periodo="Sem COVID", **kw):
    return nu.ajustar_dia(y, X, A, periodo, **kw)

def rr1(f, j=0):
    est, se, rr, lo, hi, p = nu.combinar([(f, j)], [1])
    return dict(rr=rr, lo=lo, hi=hi, p=p)

def razao(fa, ja, fb, jb):
    est, se, rr, lo, hi, p = nu.combinar([(fa, ja), (fb, jb)], [1, -1])
    return dict(rr=rr, lo=lo, hi=hi, p=p)

PARES = [("UPA", "Hospital"), ("Domicílio", "Hospital"), ("Domicílio", "UPA")]

def tabela_locais(Y, X, j=0, locais=("Todos", "Hospital", "UPA", "Domicílio"), extra=None, **kw):
    """Uma linha por local (RR) e uma por par (razão de RR). Y = {local: série diária}. Todos os ajustes nos mesmos dias."""
    F = {L: aj(Y[L], X, **kw) for L in locais}
    rows = []
    for L in locais:
        f = F[L]; r = rr1(f, j); m = kw["mask"] if kw.get("mask") is not None else A.mask[kw.get("periodo", "Sem COVID")]
        ex = X.iloc[:, j].to_numpy() > 0
        rows.append(dict(tipo="RR", a=L, b="", n=int(Y[L][m].sum()), dx=int(ex[m].sum()), obs_exp=int(Y[L][m & ex].sum()), phi=round(float(f["phi"]), 2), **r, **(extra or {})))
    for a, b in PARES:
        if a in F and b in F:
            r = razao(F[a], j, F[b], j)
            rows.append(dict(tipo="razão", a=a, b=b, n=int(Y[a][m].sum() + Y[b][m].sum()), **r, **(extra or {})))
    return rows, F

def wald_locais(F, nomes):
    st, g, p = nu.wald_homog([(F[L], 0) for L in nomes]); return dict(estat=round(st, 3), gl=g, p=p)

def excesso(y, x, periodo="Sem COVID", mask=None):
    """Óbitos em excesso nos dias expostos = observado - esperado do contrafactual sem calor (nu.ajuste_diario), com IC pelos limites do RR."""
    m = M0 if mask is None else mask
    f = nu.ajuste_diario(y, A, X=np.asarray(x, float), mask=m)
    ex = (np.asarray(x) > 0) & m
    o = float(y[ex].sum()); e = float(np.nansum(f["mu"][ex]))
    return dict(obs_exp=o, esp_exp=e, excesso=o - e, exc_lo=float(y[ex].sum() * (1 - 1 / f["lo"])), exc_hi=float(y[ex].sum() * (1 - 1 / f["hi"])),
                fa=1 - e / o if o else np.nan)

def salvar(nome, rows):
    df = pd.DataFrame(rows); df.to_csv(OUT + nome, index=False); log("salvo", nome, len(df), "linhas"); return df

# ================================================================ DESCRIÇÃO
if "desc" in PARTES:
    d = D["res"]; dm = d[d.dia.isin(dias[M0])]
    rows = []
    for nome, full in [("Todos", None)] + list(LOCS.items()):
        x = dm if full is None else dm[dm.local == LOCS[nome]]
        cv = x[x.cid.str[:2] == "I6"]
        rows.append(dict(local=nome, n=len(x), por_dia=len(x) / M0.sum(), idade_media=x.idade_anos.mean(), idade_mediana=x.idade_anos.median(),
                         pct_61mais=100 * (x.idade_anos >= 61).mean(), pct_mal_definida=100 * (x.cap == "R").mean(), pct_r99=100 * (x.cid == "R99").mean(),
                         n_cerebrovascular=len(cv), pct_cerebrovascular=100 * len(cv) / max(len(x), 1),
                         pct_i64_no_cv=100 * (cv.cid == "I64").mean() if len(cv) else np.nan, pct_i67_i69_no_cv=100 * cv.cid.isin(["I67", "I69"]).mean() if len(cv) else np.nan,
                         pct_hemorragico_no_cv=100 * cv.cid.isin(["I60", "I61", "I62"]).mean() if len(cv) else np.nan))
    salvar("desc_locais.csv", rows)
    ct_ = pd.crosstab(dm.LOCOCOR.astype("string").fillna("NA"), dm.local); ct_.to_csv(OUT + "desc_lococor_x_local.csv")
    # dias do ajuste e exclusões
    ex = {"dias_serie": len(dias), "dias_covid": int(A.covid.sum()), "dias_mes_incompleto": int(A.inc.sum()), "dias_sem_clima": int(C.sem_clima.sum()),
          "dias_ajuste_sem_covid": int(M0.sum()), "dias_ajuste_todo_periodo": int(A.mask["Todo o período"].sum()), "inicio": str(dias[0].date()), "fim": str(dias[-1].date()),
          "meses_incompletos": [str(p) for p in cx.ruins]}
    for k in EV:
        e = np.nan_to_num(EV[k]) > 0; X = EXPO[k]["dia"].iloc[:, 0].to_numpy() > 0
        ex[f"{k}_dias_evento"] = int(e[M0].sum()); ex[f"{k}_dias_expostos"] = int(X[M0].sum())
    ex["nc_dist"] = {int(k): int(v) for k, v in pd.Series(NC[M0]).value_counts().sort_index().items()}
    w = EXPO["ic"]["onda"]; ex["ic_isolado_dias"] = int((w.iloc[:, 0] > 0)[M0].sum()); ex["ic_onda_dias"] = int((w.iloc[:, 1] > 0)[M0].sum())
    ex["n_residentes_naturais_ajuste"] = int(len(dm)); ex["n_todos_naturais"] = int(len(D["todos"][D["todos"].dia.isin(dias[M0])]))
    # estações e rede (informativo): média de estações por ano já está no painel
    json.dump(ex, open(OUT + "desc_exclusoes.json", "w"), ensure_ascii=False, indent=1)
    log("desc ok")

# ================================================================ ARTIGO 2: locais (todas as causas naturais)
if "locais" in PARTES:
    rows = []
    for dk in ("ic", "an"):
        X = EXPO[dk]["dia"]
        Y = {L: serie(D["res"], L) for L in ["Todos", "Hospital", "UPA", "Domicílio", "Outros estab.", "Outros locais", "Via pública"]}
        r, F = tabela_locais(Y, X, locais=("Todos", "Hospital", "UPA", "Domicílio", "Outros estab.", "Outros locais", "Via pública"), extra=dict(definicao=NOMES_DEF[dk]))
        # excesso por local
        for row in r:
            if row["tipo"] == "RR":
                e = excesso(Y[row["a"]], X.iloc[:, 0].to_numpy()); row.update({k: v for k, v in e.items() if k in ("esp_exp", "excesso", "exc_lo", "exc_hi", "fa")})
        # as razões contra o hospital para os demais locais
        for L in ("Outros estab.", "Outros locais", "Via pública"):
            q = razao(F[L], 0, F["Hospital"], 0); r.append(dict(tipo="razão", a=L, b="Hospital", definicao=NOMES_DEF[dk], **q))
        w1 = wald_locais(F, ["Hospital", "UPA", "Domicílio"]); w2 = wald_locais(F, ["Hospital", "UPA", "Outros estab.", "Domicílio", "Outros locais"])
        r.append(dict(tipo="Wald", a="Hospital, UPA, Domicílio", definicao=NOMES_DEF[dk], **{f"w_{k}": v for k, v in w1.items()}))
        r.append(dict(tipo="Wald", a="Hospital, UPA, Outros estab., Domicílio, Outros locais", definicao=NOMES_DEF[dk], **{f"w_{k}": v for k, v in w2.items()}))
        rows += r
    # recorte por pop "todos" e "Todo o período": ver parte sens
    salvar("locais.csv", rows)

# ================================================================ defasagem 0 a 7
NL = 8
def ajustar_lags(Y, ev, periodo="Sem COVID"):
    X = pd.DataFrame({f"lag{k}": pd.Series(np.nan_to_num(ev)).shift(k).fillna(0).to_numpy() for k in range(NL)})
    nan = pd.Series(np.isnan(ev).astype(float)).rolling(NL, min_periods=1).max().to_numpy() > 0
    m = A.mask[periodo] & ~nan
    p_ = nu.controles_diarios(dias, m, A.df_ano)[0].shape[1]
    cum = lambda a, b: np.r_[np.zeros(a), np.ones(b - a + 1), np.zeros(NL - b - 1 + p_)]
    cont = np.vstack([np.r_[np.eye(NL)[k], np.zeros(p_)] for k in range(NL)] + [cum(0, 1), cum(0, 3), cum(0, NL - 1)])
    nomes = [f"lag{k}" for k in range(NL)] + ["cum01", "cum03", "cum07"]
    F = {L: aj(y, X, periodo, mask=m, contrastes=cont) for L, y in Y.items()}
    return F, nomes, m

def linhas_lag(F, nomes, extra, locais):
    rows = []
    for j, nm in enumerate(nomes):
        for L in locais:
            rows.append(dict(tipo="RR", termo=nm, a=L, **rr1(F[L], j), **extra))
        for a, b in PARES:
            if a in F and b in F: rows.append(dict(tipo="razão", termo=nm, a=a, b=b, **razao(F[a], j, F[b], j), **extra))
    return rows

if "lag" in PARTES:
    rows = []
    Y = {L: serie(D["res"], L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
    for dk in ("ic", "an"):
        F, nomes, m = ajustar_lags(Y, EV[dk]); rows += linhas_lag(F, nomes, dict(definicao=NOMES_DEF[dk], desfecho="Causas naturais"), list(Y))
        log("lag", dk)
    # 61+ (idosos), para o artigo de idade
    for fx in ("61+", "<61"):
        Yf = {L: serie(D["res"][D["res"].idade61 == fx], L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
        F, nomes, m = ajustar_lags(Yf, EV["ic"]); rows += linhas_lag(F, nomes, dict(definicao=NOMES_DEF["ic"], desfecho=f"Causas naturais, {fx} anos"), list(Yf))
    # cerebrovascular
    dcv = D["res"][D["res"].cid.str[:2] == "I6"]
    Yc = {L: serie(dcv, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
    for dk in ("ic", "an"):
        F, nomes, m = ajustar_lags(Yc, EV[dk]); rows += linhas_lag(F, nomes, dict(definicao=NOMES_DEF[dk], desfecho="Doenças cerebrovasculares (I60–I69)"), list(Yc))
    salvar("lag.csv", rows)

# ================================================================ definições de calor
if "defs" in PARTES:
    rows = []
    desf = {"Causas naturais": D["res"], "Doenças cerebrovasculares (I60–I69)": D["res"][D["res"].cid.str[:2] == "I6"]}
    for nd, dd in desf.items():
        Y = {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
        for dk in EV:
            for esq, X in EXPO[dk].items():
                for j, col in enumerate(X.columns):
                    ex = X.iloc[:, j].to_numpy() > 0
                    if ex[M0].sum() < nu.MIN_DIAS_EXPOSTOS: continue
                    F = {L: aj(Y[L], X) for L in Y}
                    for L in Y: rows.append(dict(tipo="RR", desfecho=nd, definicao=NOMES_DEF[dk], esquema=esq, termo=col, a=L, dx=int(ex[M0].sum()), obs_exp=int(Y[L][M0 & ex].sum()), **rr1(F[L], j)))
                    for a, b in PARES: rows.append(dict(tipo="razão", desfecho=nd, definicao=NOMES_DEF[dk], esquema=esq, termo=col, a=a, b=b, dx=int(ex[M0].sum()), **razao(F[a], j, F[b], j)))
        log("defs", nd)
    salvar("defs.csv", rows)

# ================================================================ sensibilidade
def binomial_condicional(ya, yb, X, j=0, lags=14):
    """Logit da fração de óbitos no local a entre a+b em função do calor: exp(beta) = razão de RR (a/b) se as séries forem Poisson. Usa só o total do dia
    como denominador, então não depende do nível geral de mortalidade. Spline de tempo e dia da semana comuns."""
    m = M0; Cm = A.controles("Sem COVID")
    y2 = np.column_stack([ya[m], yb[m]]); ok = y2.sum(1) > 0
    xx = np.column_stack([X.iloc[:, j].to_numpy(float)[m], Cm])[ok]
    g = sm.GLM(y2[ok], xx, family=sm.families.Binomial()).fit(cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True})
    b, s = float(g.params[0]), float(g.bse[0])
    return dict(rr=np.exp(b), lo=np.exp(b - 1.96 * s), hi=np.exp(b + 1.96 * s), p=float(g.pvalues[0]))

def lead_adj(y_by, ev):
    """Placebo: exposição ao calor FUTURO (eventos em t+1..t+4) incluída junto com a exposição real (t..t-3). O coeficiente do futuro deve ser ~1."""
    e = np.nan_to_num(ev).astype(bool); z = np.r_[e[1:], [False]]
    lead = nu.janela_max(z[::-1].copy())[::-1].astype(float)
    X = pd.DataFrame({"real": XIC.iloc[:, 0].to_numpy(), "futuro": lead})
    F = {L: aj(y, X) for L, y in y_by.items()}
    return F

def bateria(getY, locais, extra, ev_key="ic"):
    """Contrastes principais sob escolhas alternativas de análise. getY(pop, loc) -> série diária."""
    rows = []; X = EXPO[ev_key]["dia"]
    def reg(nome, F, j=0, grupo=""):
        for L in locais: rows.append(dict(tipo="RR", variante=nome, grupo=grupo, a=L, **rr1(F[L], j), **extra))
        for a, b in PARES:
            if a in F and b in F: rows.append(dict(tipo="razão", variante=nome, grupo=grupo, a=a, b=b, **razao(F[a], j, F[b], j), **extra))
    Y = {L: getY("res", L) for L in locais}
    reg("Base: residentes, Sem COVID, 2012–2026, 7 gl/ano, HAC 14", {L: aj(Y[L], X) for L in locais}, grupo="base")
    reg("Inclui o período COVID (Todo o período)", {L: aj(Y[L], X, "Todo o período") for L in locais}, grupo="período")
    Yt = {L: getY("todos", L) for L in locais}
    reg("Todos os óbitos ocorridos no Rio (não só residentes)", {L: aj(Yt[L], X) for L in locais}, grupo="população")
    for df in (5, 10): reg(f"Spline de tempo com {df} gl/ano", {L: aj(Y[L], X, df_ano=df) for L in locais}, grupo="controle de tendência")
    for lg in (7, 28): reg(f"EP robusto com {lg} defasagens (HAC)", {L: aj(Y[L], X, lags=lg) for L in locais}, grupo="autocorrelação")
    mk = A.mascara("Sem COVID", 2015, 2026); reg("Só 2015–2026 (rede de estações com 9–10 postos)", {L: aj(Y[L], X, mask=mk) for L in locais}, grupo="rede de estações")
    mk = A.mascara("Sem COVID", 2012, 2019); reg("Só 2012–2019 (antes da pandemia)", {L: aj(Y[L], X, mask=mk) for L in locais}, grupo="janela")
    mk = A.mascara("Sem COVID", 2022, 2026); reg("Só 2022–2026 (depois da pandemia)", {L: aj(Y[L], X, mask=mk) for L in locais}, grupo="janela")
    # exposição futura
    Fl = lead_adj(Y, EV[ev_key])
    for L in locais: rows.append(dict(tipo="RR", variante="Placebo: calor FUTURO (t+1 a t+4), ajustado pelo calor real", grupo="placebo", a=L, **rr1(Fl[L], 1), **extra))
    for a, b in PARES:
        if a in Fl and b in Fl: rows.append(dict(tipo="razão", variante="Placebo: calor FUTURO (t+1 a t+4), ajustado pelo calor real", grupo="placebo", a=a, b=b, **razao(Fl[a], 1, Fl[b], 1), **extra))
    # binomial condicional
    for a, b in PARES:
        if a in Y and b in Y:
            rows.append(dict(tipo="razão", variante="Binomial condicional (fração a/(a+b) por dia)", grupo="modelo", a=a, b=b, **binomial_condicional(Y[a], Y[b], X), **extra))
    return rows

if "sens" in PARTES:
    dres, dtod = D["res"], D["todos"]
    def gY_nat(pop, L): return serie(D[pop], L)
    rows = bateria(gY_nat, ["Hospital", "UPA", "Domicílio"], dict(desfecho="Causas naturais"))
    log("sens naturais")
    def gY_cv(pop, L): return serie(D[pop][D[pop].cid.str[:2] == "I6"], L)
    rows += bateria(gY_cv, ["Hospital", "UPA", "Domicílio"], dict(desfecho="Doenças cerebrovasculares (I60–I69)"))
    log("sens cerebrovasc")
    # causas mal definidas e classificação do local
    X = XIC; ext = dict(desfecho="Causas naturais")
    def reg_extra(nome, grupo, F, locais, extra):
        for L in locais: rows.append(dict(tipo="RR", variante=nome, grupo=grupo, a=L, **rr1(F[L], 0), **extra))
        for a, b in PARES:
            if a in F and b in F: rows.append(dict(tipo="razão", variante=nome, grupo=grupo, a=a, b=b, **razao(F[a], 0, F[b], 0), **extra))
    dsr = D["res"][D["res"].cap != "R"]; Ysr = {L: serie(dsr, L) for L in ["Hospital", "UPA", "Domicílio"]}
    reg_extra("Sem o capítulo XVIII (causas mal definidas, R00–R99)", "causa mal definida", {L: aj(Ysr[L], X) for L in Ysr}, list(Ysr), ext)
    for nome_d, dd, ex_ in [("Causas naturais", D["res"], ext), ("Doenças cerebrovasculares (I60–I69)", D["res"][D["res"].cid.str[:2] == "I6"], dict(desfecho="Doenças cerebrovasculares (I60–I69)"))]:
        lc = dd.LOCOCOR.astype("string")
        Yl = {"Estabelecimento de saúde (LOCOCOR 1 ou 2)": nu.serie_dias(dd[lc.isin(["1", "2"])], dias), "Domicílio (LOCOCOR 3)": nu.serie_dias(dd[lc == "3"], dias)}
        F = {L: aj(y, X) for L, y in Yl.items()}
        for L in Yl: rows.append(dict(tipo="RR", variante="Local só pelo LOCOCOR do SIM, sem o CNES", grupo="classificação do local", a=L, **rr1(F[L], 0), **ex_))
        a, b = list(Yl)[1], list(Yl)[0]
        rows.append(dict(tipo="razão", variante="Local só pelo LOCOCOR do SIM, sem o CNES", grupo="classificação do local", a=a, b=b, **razao(F[a], 0, F[b], 0), **ex_))
    salvar("sens.csv", rows)

# ================================================================ ARTIGO 3: idade
if "idade" in PARTES:
    rows = []; d = D["res"]
    bandas = ["0–20", "21–30", "31–40", "41–50", "51–60", "61–70", "71–80", "81+"]
    meio = {"0–20": 10, "21–30": 25.5, "31–40": 35.5, "41–50": 45.5, "51–60": 55.5, "61–70": 65.5, "71–80": 75.5, "81+": 85}
    X = XIC; FB = {}
    for b in bandas + ["61+", "<61"]:
        dd = d[d.banda == b] if b in bandas else d[d.idade61 == b]
        Y = {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
        if min(Y["Hospital"][M0].sum(), Y["Domicílio"][M0].sum(), Y["UPA"][M0].sum()) < 300:
            log("idade: faixa com poucos óbitos, não estimada", b); continue
        r, F = tabela_locais(Y, X, extra=dict(faixa=b)); FB[b] = F; rows += r
    # testes entre faixas (diferença das razões)
    if len(FB) > 1:
        bs = [b for b in bandas if b in FB]
        for a, bb, nome in [("Domicílio", "Hospital", "Domicílio/Hospital"), ("UPA", "Hospital", "UPA/Hospital"), ("Domicílio", "UPA", "Domicílio/UPA")]:
            dif = [(nu.diferenca(FB[b][a], 0, FB[b][bb], 0), 0) for b in bs]
            st, g, p = nu.wald_homog(dif)
            sl, se, pp = nu.tendencia(dif, [meio[b] / 10 for b in bs])
            rows.append(dict(tipo="homogeneidade", a=nome, faixa=" / ".join(bs), w_estat=round(st, 3), w_gl=g, p=p, tend_por_decada=sl, tend_ep=se, tend_p=pp,
                             tend_razao_por_decada=float(np.exp(sl)), tend_lo=float(np.exp(sl - 1.96 * se)), tend_hi=float(np.exp(sl + 1.96 * se))))
            # diferença entre 61+ e <61 das razões de RR (razão das razões)
            if "61+" in FB and "<61" in FB:
                d1 = nu.diferenca(FB["61+"][a], 0, FB["61+"][bb], 0); d0 = nu.diferenca(FB["<61"][a], 0, FB["<61"][bb], 0)
                q = nu.combinar([(d1, 0), (d0, 0)], [1, -1]); rows.append(dict(tipo="razão das razões 61+ vs <61", a=nome, faixa="61+ / <61", rr=q[2], lo=q[3], hi=q[4], p=q[5]))
    # idade x definição de calor, 61+ e <61
    for dk in ("ic", "an", "nc2", "nc3"):
        for fx in ("61+", "<61"):
            dd = d[d.idade61 == fx]; Y = {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
            r, F = tabela_locais(Y, EXPO[dk]["dia"], extra=dict(faixa=fx, definicao=NOMES_DEF[dk], bloco="definição")); rows += r
    salvar("idade.csv", rows)

# ================================================================ ARTIGO 4: capítulos da CID
CAPS = {  # capítulo -> função sobre (cap letra, cid de 3 caracteres)
    "I Infecciosas e parasitárias (A00–B99, sem COVID-19)": lambda c: c[0] in "AB",
    "II Neoplasias (C00–D48)": lambda c: c[0] == "C" or (c[0] == "D" and int(c[1:3]) <= 48),
    "III Sangue e imunitárias (D50–D89)": lambda c: c[0] == "D" and int(c[1:3]) >= 50,
    "IV Endócrinas, nutricionais e metabólicas (E00–E90)": lambda c: c[0] == "E",
    "V Transtornos mentais e comportamentais (F00–F99)": lambda c: c[0] == "F",
    "VI Sistema nervoso (G00–G99)": lambda c: c[0] == "G",
    "IX Aparelho circulatório (I00–I99)": lambda c: c[0] == "I",
    "X Aparelho respiratório (J00–J99)": lambda c: c[0] == "J",
    "XI Aparelho digestivo (K00–K93)": lambda c: c[0] == "K",
    "XII Pele (L00–L99)": lambda c: c[0] == "L",
    "XIII Osteomuscular (M00–M99)": lambda c: c[0] == "M",
    "XIV Aparelho geniturinário (N00–N99)": lambda c: c[0] == "N",
    "XVIII Sintomas, sinais e causas mal definidas (R00–R99)": lambda c: c[0] == "R",
}
def n3(c, a, b): return (c[0] == a[0]) and (a <= c <= b)
GRUPOS = {
    "Doenças isquêmicas do coração (I20–I25)": lambda c: n3(c, "I20", "I25"),
    "Doenças hipertensivas (I10–I15)": lambda c: n3(c, "I10", "I15"),
    "Insuficiência cardíaca (I50)": lambda c: c == "I50",
    "Demais doenças do coração (I26–I49, I51–I52)": lambda c: n3(c, "I26", "I49") or n3(c, "I51", "I52"),
    "Doenças cerebrovasculares (I60–I69)": lambda c: n3(c, "I60", "I69"),
    "Influenza e pneumonia (J09–J18)": lambda c: n3(c, "J09", "J18"),
    "Doenças crônicas das vias aéreas inferiores (J40–J47)": lambda c: n3(c, "J40", "J47"),
    "Insuficiência respiratória e outras doenças respiratórias (J19–J39, J60–J99)": lambda c: c[0] == "J" and not (n3(c, "J09", "J18") or n3(c, "J40", "J47")),
    "Diabetes mellitus (E10–E14)": lambda c: n3(c, "E10", "E14"),
    "Demências e doença de Alzheimer (F00–F03, G30)": lambda c: n3(c, "F00", "F03") or c == "G30",
    "Insuficiência renal (N17–N19)": lambda c: n3(c, "N17", "N19"),
    "Septicemia (A40–A41)": lambda c: n3(c, "A40", "A41"),
    "Neoplasias malignas (C00–C97)": lambda c: n3(c, "C00", "C97"),
}
MIN_CAP = 500
def mapa(df, fun):
    u = df.cid.unique(); ok = {c: bool(fun(c)) if c[1:3].isdigit() else False for c in u}; return df.cid.map(ok).to_numpy()

def bloco_causas(defs, nome_bloco, d, X):
    rows = []; Yd = {}
    for nome, fun in defs.items():
        dd = d[mapa(d, fun)]
        Y = {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
        nh, nu_, nd_ = (int(Y[L][M0].sum()) for L in ("Hospital", "UPA", "Domicílio"))
        base = dict(bloco=nome_bloco, causa=nome, n_hosp=nh, n_upa=nu_, n_dom=nd_)
        if min(nh, nd_) < MIN_CAP:
            rows.append(dict(tipo="não estimado", **base)); continue
        r, F = tabela_locais(Y, X, extra=base)
        for row in r:
            if row["tipo"] == "RR":
                e = excesso(Y[row["a"]], X.iloc[:, 0].to_numpy()); row.update({k: v for k, v in e.items() if k in ("esp_exp", "excesso", "exc_lo", "exc_hi", "fa")})
        rows += r
    return rows

if "cap" in PARTES:
    d = D["res"]; rows = bloco_causas(CAPS, "capítulo", d, XIC) + bloco_causas(GRUPOS, "grupo", d, XIC)
    df = pd.DataFrame(rows)
    for bl in ("capítulo", "grupo"):
        for par in (("Domicílio", "Hospital"), ("UPA", "Hospital"), ("Domicílio", "UPA")):
            s = (df.tipo == "razão") & (df.bloco == bl) & (df.a == par[0]) & (df.b == par[1])
            df.loc[s, "q_bh"] = nu.bh(df.loc[s, "p"].to_numpy())
    df.to_csv(OUT + "capitulos.csv", index=False); log("capitulos", len(df))
    # com 61+ apenas, capítulos principais
    rows = bloco_causas(CAPS, "capítulo, 61+", d[d.idade61 == "61+"], XIC); df = pd.DataFrame(rows)
    for par in (("Domicílio", "Hospital"), ("UPA", "Hospital")):
        s = (df.tipo == "razão") & (df.a == par[0]) & (df.b == par[1]); df.loc[s, "q_bh"] = nu.bh(df.loc[s, "p"].to_numpy())
    df.to_csv(OUT + "capitulos_61mais.csv", index=False)
    # com definição alternativa (anomalia térmica)
    rows = bloco_causas(CAPS, "capítulo, anomalia térmica", d, EXPO["an"]["dia"]); df = pd.DataFrame(rows)
    for par in (("Domicílio", "Hospital"), ("UPA", "Hospital")):
        s = (df.tipo == "razão") & (df.a == par[0]) & (df.b == par[1]); df.loc[s, "q_bh"] = nu.bh(df.loc[s, "p"].to_numpy())
    df.to_csv(OUT + "capitulos_anomalia.csv", index=False); log("capitulos ok")

# ---------------------------------------------------------------- ARTIGO 4, complemento: descrição, heterogeneidade entre capítulos e qualidade da causa
POUCO = ["I46", "I49", "I51", "I95", "I99"]   # códigos de 3 caracteres do capítulo IX pouco específicos (parada cardíaca, arritmias, doença cardíaca mal definida, outros)
if "capx" in PARTES:
    d = D["res"]; LS = ("Hospital", "UPA", "Domicílio"); dm = d[d.dia.isin(dias[M0])]
    # (a) óbitos por capítulo e local nos dias do ajuste, todas as idades (inclui os capítulos que não entram nos modelos)
    rows = []; usados = np.zeros(len(dm), bool)
    for nome, fun in CAPS.items():
        m = mapa(dm, fun); usados |= m
        for L in LS: rows.append(dict(causa=nome, local=L, n=int((m & (dm.local == LOCS[L]).to_numpy()).sum())))
    for L in LS: rows.append(dict(causa="Outros capítulos (VII, VIII, XV, XVI e XVII)", local=L, n=int((~usados & (dm.local == LOCS[L]).to_numpy()).sum())))
    pd.DataFrame(rows).to_csv(OUT + "desc_capitulos.csv", index=False)
    # composição do capítulo XVIII e dos códigos pouco específicos do IX por local
    rows = []
    for L in LS:
        x = dm[dm.local == LOCS[L]]
        rows.append(dict(local=L, n_total=len(x), n_cap_R=int((x.cap == "R").sum()), n_R99=int((x.cid == "R99").sum()), n_R54=int((x.cid == "R54").sum()),
                         n_cap_I=int((x.cap == "I").sum()), n_pouco_I=int(x.cid.isin(POUCO).sum()), **{f"n_{c}": int((x.cid == c).sum()) for c in POUCO}))
    pd.DataFrame(rows).to_csv(OUT + "desc_codigos.csv", index=False)
    # (b) heterogeneidade da razão entre capítulos (teste de Wald, contrastes nos mesmos dias, covariância HAC conjunta)
    FC = {}
    for nome, fun in CAPS.items():
        dd = d[mapa(d, fun)]; Y = {L: serie(dd, L) for L in LS}
        if min(Y["Hospital"][M0].sum(), Y["Domicílio"][M0].sum()) < MIN_CAP: continue
        FC[nome] = {L: aj(Y[L], XIC) for L in LS}
    rows = []
    for a, b in PARES:
        for excl_R in (False, True):
            ns = [n for n in FC if not (excl_R and n.startswith("XVIII"))]
            st, g, p = nu.wald_homog([(nu.diferenca(FC[n][a], 0, FC[n][b], 0), 0) for n in ns])
            rows.append(dict(a=a, b=b, conjunto="sem o capítulo XVIII" if excl_R else "todos os capítulos estimados", n_cap=len(ns), estat=st, gl=g, p=p))
    pd.DataFrame(rows).to_csv(OUT + "capitulos_homogeneidade.csv", index=False)
    # (c) circulatório contra os demais, e variantes de qualidade da causa
    VAR = {
        "Todas as causas naturais": d,
        "Capítulo IX (aparelho circulatório)": d[d.cap == "I"],
        "Todas as causas naturais, exceto o capítulo IX": d[d.cap != "I"],
        "Capítulo IX, sem I46, I49, I51, I95 e I99": d[(d.cap == "I") & ~d.cid.isin(POUCO)],
        "Só I46, I49, I51, I95 e I99": d[d.cid.isin(POUCO)],
        "Capítulo XVIII mais I46, I49, I51, I95 e I99": d[(d.cap == "R") | d.cid.isin(POUCO)],
        "Capítulo XVIII sem R99 e R54": d[(d.cap == "R") & ~d.cid.isin(["R99", "R54"])],
        "Todas as causas naturais, sem o capítulo XVIII e sem I46, I49, I51, I95 e I99": d[~((d.cap == "R") | d.cid.isin(POUCO))],
    }
    rows = []; FV = {}
    for nome, dd in VAR.items():
        Y = {L: serie(dd, L) for L in LS}
        r, F = tabela_locais(Y, XIC, locais=LS, extra=dict(variante=nome)); FV[nome] = F
        for row in r:
            if row["tipo"] == "RR":
                e = excesso(Y[row["a"]], XIC.iloc[:, 0].to_numpy()); row.update({k: v for k, v in e.items() if k in ("esp_exp", "excesso", "exc_lo", "exc_hi", "fa")})
        rows += r
    for a, b in PARES:                               # razão das razões: capítulo IX contra os demais e contra as neoplasias
        for nome2, F2 in [("Todas as causas naturais, exceto o capítulo IX", FV["Todas as causas naturais, exceto o capítulo IX"]), ("II Neoplasias (C00–D48)", FC["II Neoplasias (C00–D48)"])]:
            q = nu.combinar([(nu.diferenca(FV["Capítulo IX (aparelho circulatório)"][a], 0, FV["Capítulo IX (aparelho circulatório)"][b], 0), 0), (nu.diferenca(F2[a], 0, F2[b], 0), 0)], [1, -1])
            rows.append(dict(tipo="razão das razões", a=a, b=b, variante="Capítulo IX contra " + nome2, rr=q[2], lo=q[3], hi=q[4], p=q[5]))
    pd.DataFrame(rows).to_csv(OUT + "capitulos_qualidade.csv", index=False); log("capx ok")

# ================================================================ ARTIGO 1: cerebrovasculares
SUBTIPOS = {
    "Doenças cerebrovasculares (I60–I69)": lambda c: n3(c, "I60", "I69"),
    "AVC agudo ou não especificado (I60–I64)": lambda c: n3(c, "I60", "I64"),
    "Hemorrágico (I60–I62)": lambda c: n3(c, "I60", "I62"),
    "AVC não especificado como hemorrágico ou isquêmico (I64)": lambda c: c == "I64",
    "Outras doenças cerebrovasculares (I65–I68, sem I69)": lambda c: n3(c, "I65", "I68"),
    "Sequelas de doenças cerebrovasculares (I69)": lambda c: c == "I69",
}
if "cv" in PARTES:
    d = D["res"]; dcv = d[d.cid.str[:2] == "I6"]
    rows = []
    for nome, fun in SUBTIPOS.items():
        dd = d[mapa(d, fun)]
        Y = {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
        base = dict(bloco="subtipo", causa=nome, n_hosp=int(Y["Hospital"][M0].sum()), n_upa=int(Y["UPA"][M0].sum()), n_dom=int(Y["Domicílio"][M0].sum()))
        if min(base["n_upa"], base["n_dom"]) < 300:
            for L in ("Hospital", "UPA", "Domicílio"):    # mostra o que for estimável, marcando a baixa contagem
                pass
        r, F = tabela_locais(Y, XIC, extra=base)
        if min(base["n_upa"], base["n_dom"]) < 300:
            for x in r: x["aviso"] = "menos de 300 óbitos em pelo menos um local: estimativa instável"
        rows += r
    # idade
    Ycv = lambda dd: {L: serie(dd, L) for L in ["Todos", "Hospital", "UPA", "Domicílio"]}
    bandas = {"<61": dcv[dcv.idade_anos < 61], "61–80": dcv[(dcv.idade_anos >= 61) & (dcv.idade_anos < 81)], "81+": dcv[dcv.idade_anos >= 81], "61+": dcv[dcv.idade_anos >= 61]}
    FB = {}
    for b, dd in bandas.items():
        Y = Ycv(dd); base = dict(bloco="idade", causa="Doenças cerebrovasculares (I60–I69)", faixa=b, n_hosp=int(Y["Hospital"][M0].sum()), n_upa=int(Y["UPA"][M0].sum()), n_dom=int(Y["Domicílio"][M0].sum()))
        r, F = tabela_locais(Y, XIC, extra=base); FB[b] = F; rows += r
    for a, bb, nome in [("Domicílio", "Hospital", "Domicílio/Hospital"), ("UPA", "Hospital", "UPA/Hospital"), ("Domicílio", "UPA", "Domicílio/UPA")]:
        d1 = nu.diferenca(FB["61–80"][a], 0, FB["61–80"][bb], 0); d2 = nu.diferenca(FB["81+"][a], 0, FB["81+"][bb], 0); d0 = nu.diferenca(FB["<61"][a], 0, FB["<61"][bb], 0)
        st, g, p = nu.wald_homog([(d0, 0), (d1, 0), (d2, 0)]); rows.append(dict(bloco="idade", tipo="homogeneidade", causa="Doenças cerebrovasculares (I60–I69)", a=nome, w_estat=round(st, 3), w_gl=g, p=p))
    # definições de calor
    Y = Ycv(dcv)
    for dk in ("ic", "an", "nc2", "nc3"):
        r, F = tabela_locais(Y, EXPO[dk]["dia"], extra=dict(bloco="definição", causa="Doenças cerebrovasculares (I60–I69)", definicao=NOMES_DEF[dk])); rows += r
    # Wald de heterogeneidade entre os 3 locais e excesso
    r, F = tabela_locais(Y, XIC, extra=dict(bloco="principal", causa="Doenças cerebrovasculares (I60–I69)"))
    for row in r:
        if row["tipo"] == "RR":
            e = excesso(Y[row["a"]], XIC.iloc[:, 0].to_numpy()); row.update({k: v for k, v in e.items() if k in ("esp_exp", "excesso", "exc_lo", "exc_hi", "fa")})
    w = wald_locais(F, ["Hospital", "UPA", "Domicílio"]); r.append(dict(bloco="principal", tipo="Wald", a="Hospital, UPA, Domicílio", **{f"w_{k}": v for k, v in w.items()}))
    rows += r
    # contraste agrupado: fora do hospital (UPA + domicílio) contra hospital, que ganha poder ao somar as duas séries pequenas
    for dk in ("ic", "an", "nc2"):
        X = EXPO[dk]["dia"]; Yc3 = {"Hospital": Y["Hospital"], "Fora do hospital (UPA + domicílio)": Y["UPA"] + Y["Domicílio"], "Domicílio": Y["Domicílio"], "UPA": Y["UPA"]}
        F = {L: aj(y, X) for L, y in Yc3.items()}
        ex_ = dict(bloco="agrupado", causa="Doenças cerebrovasculares (I60–I69)", definicao=NOMES_DEF[dk])
        for L in ("Hospital", "Fora do hospital (UPA + domicílio)"): rows.append(dict(tipo="RR", a=L, **rr1(F[L], 0), **ex_))
        rows.append(dict(tipo="razão", a="Fora do hospital (UPA + domicílio)", b="Hospital", **razao(F["Fora do hospital (UPA + domicílio)"], 0, F["Hospital"], 0), **ex_))
    salvar("cerebrovascular.csv", rows)

log("fim", PARTES)
