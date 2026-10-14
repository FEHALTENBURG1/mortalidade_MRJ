#!/usr/bin/env python3
"""Monta o painel HTML autocontido a partir das tabelas calculadas (pasta analise/) e do modelo painel_template.html.
Uso: python merge_html.py [pasta_analise] [saida.html]"""
import sys, os, json, re, datetime, gzip, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import nucleo as nu
AQUI = os.path.dirname(os.path.abspath(__file__))
A = (sys.argv[1] if len(sys.argv) > 1 else "analise") + "/"; SAIDA = sys.argv[2] if len(sys.argv) > 2 else A + "painel_calor_mrj.html"
pops = [p for p in ("res", "todos") if os.path.exists(A + f"dados_painel_{p}.json")]
P = {p: json.load(open(A + f"dados_painel_{p}.json")) for p in pops}
b = P["res"]
locais = [l for l in b["locais"] if l != "Ignorado"]
D = dict(semanas=b["semanas"], clima=b["clima"], climaanual=b["climaanual"], locais=locais, faixas=b["faixas"], contorno=json.load(open(A + "contorno_rio_simpl.json")), pops={})
g = pd.read_csv(A + "resumo_gam.csv", index_col=0)
D["gam"] = {v: [float(g.loc[v, "tendencia_c_por_decada"]), float(g.loc[v, "ic95_inf_c_por_decada"]), float(g.loc[v, "ic95_sup_c_por_decada"])] for v in ("t_med", "hi_med")}
aux = os.path.join(AQUI, "dados_auxiliares", "cid_nomes.json")
D["cidnomes"] = json.load(open(aux if os.path.exists(aux) else "cid_nomes.json"))
D["cid"], D["heat"], D["lag"] = [], [], []
for p in pops:
    q = P[p]; u = json.load(open(A + f"unidades_{p}.json"))
    D["pops"][p] = dict(rr=q["rr"], dias_ext=q["dias_ext"], unidades=u["unidades"], bairros=u["bairros"], cobertura=u["cobertura"], uj=u["uj"],
                        cidsem=json.load(open(A + f"cid_semanal_{p}.json")), meta=q["meta"])
    if os.path.exists(A + f"serie1_{p}.json"):         # Figura 1 desde 2006, semanal e diária (serie1.py): gzip + base64, lida sob demanda
        raw = open(A + f"serie1_{p}.json", "rb").read()
        D["pops"][p]["f1"] = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode()
        if "anos1" not in D: D["anos1"] = sorted(set(json.loads(raw)["sem"]["ano"]))
    R = pd.read_csv(A + f"cid_rr_{p}.csv")
    D["cid"] += [dict(p=r.pop, f=r.faixa, l=r.l, i=bool(r.sensivel), a=bool(r.natural), c=r.cid, s=r.sens, d=r.definicao, x=r.esquema, t=r.termo, rr=round(r.rr, 4), lo=round(r.lo, 4), hi=round(r.hi, 4),
                      q=round(r.q, 5), n=int(r.n), dx=int(r.obs_exp)) for r in R.itertuples()]
    H = pd.read_csv(A + f"heatmap_horas_{p}.csv")
    D["heat"] += [[r.pop, r.local, r.faixa, r.periodo, int(r.limiar), int(r.horas), r.rr, r.lo, r.hi, int(r.n), int(r.dias_expostos)] for r in H.itertuples()]
    L = pd.read_csv(A + f"defasagem_{p}.csv")
    D["lag"] += [[r.pop, r.local, r.faixa, r.periodo, r.definicao, r.termo, r.rr, r.lo, r.hi, int(r.n)] for r in L.itertuples()]
D["met"] = json.load(open(A + "metodos_numeros.json"))

# ---------- janelas de anos (janelas.py): colunas em inteiros + gzip + base64, uma peça por (tabela, população, janela)
JAN = dict(grade=[], b={}, min_dias=nu.MIN_DIAS_JANELA)
ESC = ("rr", "lo", "hi", "q")
def empacotar(g, cols, strs):
    k, u, c = [], {}, []
    for col in cols.split():
        s_ = g[col]; k.append(col)
        if col in strs.split():
            vals = list(dict.fromkeys(s_)); ix = {v: i for i, v in enumerate(vals)}; u[col] = vals; c.append([ix[v] for v in s_])
        elif col in ESC: c.append([int(round(float(v) * 1e4)) if v == v else 0 for v in s_])
        else: c.append([int(v) for v in s_])
    return base64.b64encode(gzip.compress(json.dumps(dict(k=k, u=u, c=c), ensure_ascii=False, separators=(",", ":")).encode(), 9, mtime=0)).decode()
ESPEC = {"rr": ("d x s l f t rr lo hi n dx ox", "d x s l f t"), "lag": ("l f s d t rr lo hi n", "l f s d t"),
         "heat": ("l f s limiar horas rr lo hi n dx", "l f s"), "cid": ("faixa l c s d x t rr lo hi q n dx ox a i", "faixa l c s d x t")}
for p in pops:
    if not os.path.exists(A + f"jan_grade_{p}.csv"): continue
    G = pd.read_csv(A + f"jan_grade_{p}.csv")
    if not JAN["grade"]:
        JAN["grade"] = [dict(y0=int(r.y0), y1=int(r.y1), sc=int(r.dias_sem_covid), td=int(r.dias_todo), pe=bool(r.pesada)) for r in G.itertuples()]
    for tab, (cols, strs) in ESPEC.items():
        f = A + f"jan_{tab}_{p}.csv.gz"
        if not os.path.exists(f): continue
        T_ = pd.read_csv(f)
        for (y0, y1), g in T_.groupby(["y0", "y1"]):
            JAN["b"][f"{tab}|{p}|{y0}-{y1}"] = empacotar(g, cols, strs)
D["jan"] = JAN
print("janelas:", len(JAN["grade"]), "|", len(JAN["b"]), "tabelas compactadas |", round(sum(len(v) for v in JAN["b"].values()) / 1e6, 2), "MB (base64)")
if "nc" not in D["clima"] and os.path.exists("heat/data/temp_df.csv"):
    th = pd.read_csv("heat/data/temp_df.csv", parse_dates=["dia"]).set_index("dia").reindex(pd.to_datetime(D["clima"]["dia"]))
    D["clima"]["nc"] = [None if v != v else int(v) for v in nu.nivel_calor(th)]
cl = D["clima"]; ini, fim = cl["dia"][0], cl["dia"][-1]; fd = lambda s: "/".join(s.split("-")[::-1])
mes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
src = json.load(open("meta_fontes.json")) if os.path.exists("meta_fontes.json") else {}
sha = lambda h: (h[:8] + "…" + h[-6:]) if h else "não informado"
tok = {"PER_CURTO": f"{ini[:4]} a {mes[int(fim[5:7]) - 1]}/{fim[:4]}", "PER_LONGO_TXT": f"de {fd(ini)} a {fd(fim)}", "COVID_TXT": f"{fd(nu.COVID[0])} a {fd(nu.COVID[1])}",
       "SHA_SILVER": sha(src.get("silver_sha256", "78913f77d85bbc219ec5fd8441fa4c53d647e904167bdc0eeda76d5d35f4d247")), "SHA_HAAT": sha(src.get("haat_sha256", "fbf926f7ed62c290c3728ea753da6d37f24135c2a673ca105f50fbb2c08843f8")),
       "ATUALIZACAO": f"esta versão em HTML é uma fotografia gerada em {datetime.date.today().strftime('%d/%m/%Y')} a partir dos Releases <code>sim-mrj</code> e <code>clima-mrj</code>. A versão em Shiny lê as tabelas pré-calculadas direto do Release <code>painel-mrj</code> do GitHub, que um workflow recalcula quando o SIM ou o clima são atualizados, sem edição manual."}
t = open(os.path.join(AQUI, "painel_template.html")).read().replace("/*DADOS*/", json.dumps(D, ensure_ascii=False, separators=(",", ":")))
for k, v in tok.items(): t = t.replace("{{" + k + "}}", v)
left = re.findall(r"\{\{\w+\}\}", t); assert not left, left
open(SAIDA, "w").write(t); print("ok", SAIDA, len(t) // 1024, "KB;", len(D["cid"]), "linhas CID;", len(D["heat"]), "heat;", len(D["lag"]), "lag")
