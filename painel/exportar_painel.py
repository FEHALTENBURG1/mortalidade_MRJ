"""Exporta as tabelas do painel (CSV/JSON) lidas pelo app Shiny. Uso: python exportar_painel.py [pasta_saida]"""
import json, sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import nucleo as nu
A = "analise/"; OUT = sys.argv[1] if len(sys.argv) > 1 else "painel_dados"; os.makedirs(OUT, exist_ok=True)
pops = ("res", "todos"); P = {p: json.load(open(A + f"dados_painel_{p}.json")) for p in pops}; U = {p: json.load(open(A + f"unidades_{p}.json")) for p in pops}
# --- semanas, clima
S = P["res"]["semanas"]; pd.DataFrame(S).to_csv(f"{OUT}/semanas.csv", index=False)
C = P["res"]["clima"]; cd = pd.DataFrame({"dia": C["dia"], "hi_max": C["hi_max"]})
if "nc" in C: cd["nivel_calor"] = C["nc"]
for v in ("t_med", "hi_med"):
    for k in ("o", "e", "sd", "z"): cd[f"{v}_{k}"] = C[v][k]
cd.to_csv(f"{OUT}/clima_diario.csv", index=False)
pd.DataFrame(P["res"]["climaanual"]).to_csv(f"{OUT}/clima_anual.csv", index=False)
g = pd.read_csv(A + "resumo_gam.csv", index_col=0)
g = g.loc[["t_med", "hi_med"], ["tendencia_c_por_decada", "ic95_inf_c_por_decada", "ic95_sup_c_por_decada"]].reset_index(); g.columns = ["variavel", "tendencia", "ic_inf", "ic_sup"]; g.to_csv(f"{OUT}/gam.csv", index=False)
# --- série semanal e RR por local x faixa
sw, rr = [], []
for p in pops:
    for k, v in P[p]["series"].items():
        L, F = k.split("|")
        sw.append(pd.DataFrame({"pop": p, "local": L, "faixa": F, "ini": S["ini"], "obs": v["o"], "esp": v["e"], "lo": v["l"], "up": v["u"]}))   # None vira vazio (semana fora do ajuste)
    rr += [dict(pop=p, definicao=r["d"], esquema=r["x"], periodo=r["s"], local=r["l"], faixa=r["f"], termo=r["t"], rr=r["rr"], lo=r["lo"], hi=r["hi"], p=r["p"], n=r["n"], dias_expostos=r["dx"], obitos_expostos=r["ox"]) for r in P[p]["rr"]]
pd.concat(sw).to_csv(f"{OUT}/serie_semanal.csv.gz", index=False); pd.DataFrame(rr).to_csv(f"{OUT}/rr_local_faixa.csv", index=False)
# --- série diária (serie1.py): observado e esperado sem calor por dia (desde 2006), para cada local x faixa e definição de calor (lag 0 a 3)
sd = []
for p in pops:
    if not os.path.exists(A + f"serie1_{p}.json"): continue
    Dd = json.load(open(A + f"serie1_{p}.json"))
    for i, k in enumerate(Dd["k"]):
        L, F, *R_ = k.split("|")                               # 'local|faixa' ou 'local|faixa|raça/cor'
        t = pd.DataFrame({"pop": p, "local": L, "faixa": F, "raca": R_[0] if R_ else "Todas", "dia": Dd["dias"], "obs": Dd["o"][i]})
        for dn in ("ic", "an", "nc"):
            t["esp_" + dn] = [None if v is None else v / 10 for v in Dd["e"][dn][i]]
        sd.append(t)
if sd: pd.concat(sd, ignore_index=True).to_csv(f"{OUT}/serie_diaria.csv.gz", index=False)
pd.concat([pd.read_csv(A + f"heatmap_horas_{p}.csv") for p in pops]).to_csv(f"{OUT}/heatmap_horas.csv", index=False)
pd.concat([pd.read_csv(A + f"defasagem_{p}.csv") for p in pops]).to_csv(f"{OUT}/defasagem.csv", index=False)
# --- CIDs
cid = [pd.read_csv(A + f"cid_rr_{p}.csv").rename(columns={"l": "local", "sens": "periodo", "obs_exp": "obitos_expostos", "dx": "dias_expostos"}) for p in pops]
pd.concat(cid, ignore_index=True).to_csv(f"{OUT}/cid_rr.csv.gz", index=False)
sem = []
for p in pops:
    for k, v in json.load(open(A + f"cid_semanal_{p}.json")).items():
        c, L = k.split("|"); e = np.array([np.nan if x is None else x for x in v["e"]], float)
        sem.append(pd.DataFrame({"pop": p, "local": L, "cid": c, "ini": S["ini"], "obs": v["o"], "esp": v["e"], "up": np.round(e + 1.96 * np.sqrt(v["phi"] * e), 1)}))
pd.concat(sem).to_csv(f"{OUT}/cid_semanal.csv.gz", index=False)
nomes = json.load(open("cid_nomes.json")); pd.DataFrame({"cid": list(nomes), "nome": list(nomes.values())}).to_csv(f"{OUT}/cid_nomes.csv", index=False)
# --- unidades, bairros, janelas
un, ba, jn = [], [], []
for p in pops:
    for u in U[p]["unidades"]:
        row = dict(pop=p, cnes=u["c"], nome=u["nome"], bairro=u["bairro"], lat=u["lat"], lon=u["lon"], tipo=u["tp"], n=u["n"], ativo_ini=(u["ativo"] or [None, None])[0], ativo_fim=(u["ativo"] or [None, None])[1], motivo=u["motivo"])
        un.append(row)
    for b in U[p]["bairros"]:
        base = dict(pop=p, bairro=b["b"], n=b["n"], hosp=b["hosp"], upa=b["upa"], out=b["out"], unidades=b["nu"], n_rr=b["n_rr"])
        if b["rr"]:
            for d, v in b["rr"].items(): ba.append({**base, "definicao": d, "rr": v[0], "lo": v[1], "hi": v[2]})
        else: ba.append(base)
    uj = U[p]["uj"]; dias = uj["dias"]
    for c, dd in uj["u"].items():
        for dn, v in dd.items():
            jn.append(pd.DataFrame({"pop": p, "cnes": c, "definicao": dn, "dia": [dias[i] for i in uj["idx"][dn]], "obs": v["o"], "esp": v["m"], "phi": v["phi"]}))
pd.DataFrame(un).to_csv(f"{OUT}/unidades.csv", index=False); pd.DataFrame(ba).to_csv(f"{OUT}/bairros.csv", index=False); pd.concat(jn).to_csv(f"{OUT}/unid_janela.csv.gz", index=False)
for p in pops: json.dump(U[p]["cobertura"], open(f"{OUT}/cobertura_{p}.json", "w"))
# --- janelas de anos (janelas.py): tabelas longas, uma linha por janela; o painel HTML as embute, o Shiny pode lê-las no futuro
for tab in ("grade", "rr", "lag", "heat", "cid"):
    fs = [A + f"jan_{tab}_{p}" + (".csv" if tab == "grade" else ".csv.gz") for p in pops]
    if all(os.path.exists(f) for f in fs):
        pd.concat([pd.read_csv(f).assign(pop=p) for f, p in zip(fs, pops)], ignore_index=True).to_csv(f"{OUT}/janelas_{tab}.csv" + ("" if tab == "grade" else ".gz"), index=False)
# --- números da aba Métodos e meta
json.dump(json.load(open(A + "metodos_numeros.json")), open(f"{OUT}/metodos_numeros.json", "w"), ensure_ascii=False, indent=1)
m = P["res"]["meta"]
meta = dict(gerado_em=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), periodo_ini=str(cd.dia.iloc[0]), periodo_fim=str(cd.dia.iloc[-1]), meses_fora=m["meses_fora"], n_semanas=len(S["ini"]),
            n_dias_modelo=m["n_dias_modelo"], n_obitos_res=P["res"]["meta"]["n_obitos"], n_obitos_todos=P["todos"]["meta"]["n_obitos"], dias_evento=P["res"]["dias_ext"],
            fontes=json.load(open("meta_fontes.json")) if os.path.exists("meta_fontes.json") else {}, definicoes=nu.DEFS)
json.dump(meta, open(f"{OUT}/meta.json", "w"), ensure_ascii=False, indent=1)
print("ok", OUT, sorted(os.listdir(OUT)))
