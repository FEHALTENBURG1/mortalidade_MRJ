#!/usr/bin/env python3
"""Conferência independente dos denominadores, das causas (CID-10) e das datas do painel.

Recalcula, em Python (pandas) e direto do Parquet do SIM e do CSV do clima, as tabelas que o painel usa, seguindo as regras escritas na aba Métodos, e compara
com o JSON gerado pelo R (calcular_figura1.R). Nada aqui chama o código do painel nem lê um gráfico: cada tabela vem dos dados brutos.

Uso, a partir da pasta painel_quarto:
  python3 testes/conferir_independente.py --silver pasta/silver --haat haat_diario_municipal.csv --json saida/figura1_res.json [--pop res]
         [--cidlista pasta_com_cid_<causa>.json] [--saida docs/conferencia_independente.md]
O --cidlista é opcional: pasta com os arquivos cid_naturais.json, cid_externas.json, cid_todas_sem_covid.json e cid_todas.json (payload "cidlista" do serviço,
gravados por testes/registrar_resultados.R --cidlista), para conferir também a lista de causas da aba Causas específicas.

Confere: período e número de dias; óbitos totais e por grupo de causa (tabela de reconciliação); a série diária de cada um dos recortes (local, faixa etária,
raça/cor) e a série semanal; dias sem registro no SIM; meses de registro não consolidado; dias sem dado de clima; Nível de Calor reconstruído; recortes elegíveis
(pelo menos 300 óbitos no ajuste); óbitos sem idade e distribuição de raça/cor; lista de causas (opcional)."""
import argparse, glob, json, os, re, sys
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--silver", required=True); ap.add_argument("--haat", required=True); ap.add_argument("--json", required=True)
ap.add_argument("--pop", default="res"); ap.add_argument("--cnes", default=None); ap.add_argument("--cidlista", default=None); ap.add_argument("--saida", default=None)
a = ap.parse_args()
raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cnes_csv = a.cnes or os.path.join(raiz, "dados_auxiliares", "cnes_estab.csv")
falhas = []
def checar(nome, cond, detalhe=""):
    print(("ok     " if cond else "FALHOU ") + nome + ((" | " + str(detalhe)[:400]) if (detalhe != "" and not cond) else ""), flush=True)
    if not cond: falhas.append(nome)

J = json.load(open(a.json, encoding="utf-8")); M = J["meta"]
RESUMO = os.path.join(os.path.dirname(os.path.abspath(a.json)), f"resumo_{a.pop}.json")
RES = json.load(open(RESUMO, encoding="utf-8")) if os.path.exists(RESUMO) else None

# ---------------------------------------------------------------- dados brutos
fs = sorted(glob.glob(os.path.join(a.silver, "sim/ocorrencia_mrj/ano_arquivo=20*/part-0.parquet")))
assert fs, "nenhum arquivo do SIM em " + a.silver
cols = ["DTOBITO", "idade_anos", "CAUSABAS", "LOCOCOR", "CODESTAB", "RACACOR", "ocorrencia_mrj", "residente_mrj"]
D = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
D = D[D.ocorrencia_mrj.fillna(False).astype(bool)].copy()                       # óbitos ocorridos no município
D["dia"] = pd.to_datetime(D.DTOBITO).dt.normalize()
CL = pd.read_csv(a.haat, parse_dates=["dia"])

INICIO = pd.Timestamp("2006-01-01"); COVID = (pd.Timestamp("2020-03-01"), pd.Timestamp("2022-06-30"))
ult_clima = CL.loc[CL.hi_max.notna(), "dia"].max()
FIM = min(D.dia.max(), ult_clima)
dias = pd.date_range(INICIO, FIM, freq="D"); nd = len(dias)

# ---------------------------------------------------------------- período
checar("período: início, fim e número de dias iguais aos do painel", M["inicio"] == str(INICIO.date()) and M["fim"] == str(FIM.date()) and M["n_dias"] == nd and J["dias"][0] == M["inicio"] and J["dias"][-1] == M["fim"], (M["inicio"], M["fim"], M["n_dias"], str(FIM.date()), nd))
checar("período: o fim é o menor entre o último dia com óbito no SIM e o último dia com clima", FIM == min(D.dia.max(), ult_clima), (D.dia.max(), ult_clima))

# ---------------------------------------------------------------- população e causas
P = D[D.residente_mrj.fillna(False).astype(bool)] if a.pop == "res" else D
P = P[(P.dia >= INICIO) & (P.dia <= FIM)].copy()
x = P.CAUSABAS.fillna("").astype(str).str.upper().str.strip().str.replace(".", "", regex=False)
x = x.where(x != "", None)
BLOCOS = [("A00", "B99"), ("C00", "D49"), ("D50", "D89"), ("E00", "E90"), ("F00", "F99"), ("G00", "G99"), ("H00", "H59"), ("H60", "H95"), ("I00", "I99"), ("J00", "J99"), ("K00", "K93"),
          ("L00", "L99"), ("M00", "M99"), ("N00", "N99"), ("O00", "O99"), ("P00", "P96"), ("Q00", "Q99"), ("R00", "R99"), ("S00", "T98"), ("U00", "U99"), ("V01", "Y98"), ("Z00", "Z99")]
def valido(c):
    if c is None or not re.fullmatch(r"[A-Z][0-9]{2}[0-9]?", c): return False
    return any(lo <= c[:3] <= hi for lo, hi in BLOCOS)
def grupo(c):                                    # a ordem de precedência da aba Métodos: ausente, inválida, COVID-19, natural, lesão, externa, outros
    if c is None: return "ausente"
    if not valido(c): return "invalida"
    if c == "B342" or c[:3] == "U07": return "covid"
    if "A" <= c[0] <= "R": return "natural"
    if c[0] in "ST": return "lesao"
    if c[0] in "VWXY": return "externa"
    return "outros_validos"
P["cid4"] = x; P["cid3"] = x.str[:3]; P["grupo"] = [grupo(c) for c in x]
tot = len(P)
rec = M["reconc"]
checar("causas: total de óbitos elegíveis igual ao da tabela de reconciliação", rec["total"] == tot, (rec["total"], tot))
cont = P.grupo.value_counts().to_dict()
dif = {g["grupo"]: (g["n"], int(cont.get(g["grupo"], 0))) for g in rec["grupos"] if g["n"] != int(cont.get(g["grupo"], 0))}
checar("causas: contagem de cada grupo de causa básica igual à da tabela de reconciliação", not dif, dif)
det = {d["rotulo"]: d["n"] for d in rec["detalhe"]}
c4 = P.cid4.fillna("")
checar("causas: B34.2 e U07 (COVID-19) e os demais B34, contados à parte", det["B34.2 (COVID-19)"] == int((c4 == "B342").sum()) and det["U07 (COVID-19)"] == int((c4.str[:3] == "U07").sum())
       and [v for k, v in det.items() if k.startswith("Demais B34")][0] == int(((c4.str[:3] == "B34") & (c4 != "B342")).sum()), (det, int((c4 == "B342").sum())))
N = P[P.grupo == "natural"]
checar("causas: o total de causas naturais é o n_obitos do painel", M["n_obitos"] == len(N), (M["n_obitos"], len(N)))

# ---------------------------------------------------------------- local, faixa e raça/cor
LOCAIS = ["Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais", "Ignorado"]
FAIXAS = ["0-4", "5-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]
CN = pd.read_csv(cnes_csv, dtype=str); CN["CODESTAB"] = CN.CODESTAB.str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(7)
CN["tipo"] = pd.to_numeric(CN.tipo, errors="coerce"); CN = CN.drop_duplicates("CODESTAB").set_index("CODESTAB").tipo
def local(df):
    tipo = df.CODESTAB.fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(7).map(CN)
    l = df.LOCOCOR.astype("string")
    out = pd.Series("Outros estabelecimentos de saúde", index=df.index)
    out[tipo.isin([5, 7, 15, 62])] = "Hospital"; out[tipo.isin([20, 21, 73])] = "UPA / pronto atendimento"
    out[tipo.isna() & (l == "1").fillna(False)] = "Hospital"
    out[(l == "3").fillna(False)] = "Domicílio"; out[(l == "4").fillna(False)] = "Via pública"; out[l.isin(["5", "6"]).fillna(False)] = "Outros locais"
    out[l.isna() | (l == "9").fillna(False)] = "Ignorado"
    return out
N = N.copy(); N["local"] = local(N)
N["faixa"] = pd.cut(pd.to_numeric(N.idade_anos, errors="coerce"), [-np.inf, 5, 10, 20, 30, 40, 50, 60, 70, 80, np.inf], right=False, labels=FAIXAS)
RACA = {"1": "Branca", "2": "Preta", "3": "Amarela", "4": "Parda", "5": "Indígena"}
N["raca"] = N.RACACOR.fillna("").astype(str).str.strip().str[:1].map(RACA).fillna("Ignorada")
checar("raça/cor: distribuição dos óbitos por causas naturais igual à do painel", {k: int(v) for k, v in N.raca.value_counts().items()} == {k: v for k, v in J["rc"].items()}, (N.raca.value_counts().to_dict(), J["rc"]))
if RES: checar("faixa etária: óbitos sem idade informada iguais ao do painel", int(N.faixa.isna().sum()) == RES["n_sem_idade"], (int(N.faixa.isna().sum()), RES["n_sem_idade"]))

idx = {d: i for i, d in enumerate(dias)}
def serie(df):
    v = np.zeros(nd, dtype=int); c = df.dia.map(idx).dropna().astype(int).value_counts()
    v[c.index.to_numpy()] = c.to_numpy(); return v
PPI = ["Preta", "Parda", "Indígena"]
S = {}
for L in ["Todos os locais"] + LOCAIS:
    dl = N if L == "Todos os locais" else N[N.local == L]
    S[f"{L}|Todas as idades"] = serie(dl)
    for fx in FAIXAS: S[f"{L}|{fx}"] = serie(dl[dl.faixa == fx])
    for r in ["Branca", "Preta", "Parda", "PPI"]: S[f"{L}|Todas as idades|{r}"] = serie(dl[dl.raca.isin(PPI)] if r == "PPI" else dl[dl.raca == r])

# ---------------------------------------------------------------- datas: dias sem registro, meses não consolidados, dias sem clima
todos_dias_obito = D.dia[D.dia >= INICIO]
com_registro = set(todos_dias_obito.unique())
sem_registro = np.array([d not in com_registro for d in dias])
checar("datas: dias sem nenhum óbito no SIM (qualquer residência) iguais aos do painel", int(sem_registro.sum()) == M["dias_sem_registro"] and sem_registro.astype(int).tolist() == J["fl"]["inc"], (int(sem_registro.sum()), M["dias_sem_registro"]))

def meses_nc(d):                                  # regras (a), (b) e (c) da aba Métodos, escritas aqui de novo a partir do texto
    d = d[d >= INICIO]; meses = pd.period_range(d.min(), d.max(), freq="M")
    n = d.dt.to_period("M").value_counts().reindex(meses, fill_value=0)
    dreg = d.drop_duplicates().dt.to_period("M").value_counts().reindex(meses, fill_value=0)
    dcal = pd.Series(pd.date_range(d.min(), d.max(), freq="D").to_period("M")).value_counts().reindex(meses, fill_value=0)
    taxa = (n / dreg.where(dreg > 0)).to_numpy()
    ult = d.max(); fim_ult = (ult.to_period("M") + 1).start_time - pd.Timedelta(days=1)
    pre = ((dreg.to_numpy() > 0) & (dreg.to_numpy() < dcal.to_numpy())) | (np.array([m == ult.to_period("M") for m in meses]) & (ult < fim_ult))
    em_covid = np.array([COVID[0].to_period("M") <= m <= COVID[1].to_period("M") for m in meses])
    ruim = pre.copy(); boas = []
    for i in range(len(meses)):
        valido_ = (not em_covid[i]) and not np.isnan(taxa[i])
        if valido_ and not pre[i] and len(boas) >= 12: ruim[i] = taxa[i] < 0.80 * np.median(boas[-12:])
        if valido_ and not ruim[i]: boas.append(taxa[i])
    return [str(m) for m, r in zip(meses, ruim) if r and m.start_time <= FIM]
mnc = meses_nc(todos_dias_obito)
checar("datas: meses de registro não consolidado iguais aos do painel", mnc == M["meses_nc"], (mnc, M["meses_nc"]))
mes_dia = np.array([str(d.to_period("M")) for d in dias])
nc_dia = np.isin(mes_dia, mnc) & ~sem_registro
checar("datas: dias de mês não consolidado (sem os dias sem registro) iguais aos do painel", int(nc_dia.sum()) == M["dias_nc"] and nc_dia.astype(int).tolist() == J["fl"]["nc"], (int(nc_dia.sum()), M["dias_nc"]))
C = CL.set_index("dia").reindex(dias)
sem_clima = C.hi_max.isna().to_numpy()
checar("datas: dias sem dado de clima iguais aos do painel", int(sem_clima.sum()) == M["dias_sem_clima"] and sem_clima.astype(int).tolist() == J["fl"]["sc"], (int(sem_clima.sum()), M["dias_sem_clima"]))
checar("datas: primeiro dia com clima observado é 17/04/2007", str(CL.loc[CL.hi_max.notna(), "dia"].min().date()) == "2007-04-17", CL.loc[CL.hi_max.notna(), "dia"].min())
covid_dia = (dias >= COVID[0]) & (dias <= COVID[1])
checar("datas: período da COVID-19 (01/03/2020 a 30/06/2022) igual ao do painel", covid_dia.astype(int).tolist() == J["fl"]["cov"] and M["covid"] == ["2020-03-01", "2022-06-30"])

# clima do painel x CSV
def igual(a_, b_, casas):
    a_ = np.array([np.nan if v is None else v for v in a_], dtype=float); b_ = b_.to_numpy(float)       # o painel guarda o valor arredondado: a diferença para o CSV é de no máximo meia casa decimal
    return bool(np.all((np.isnan(a_) & np.isnan(b_)) | (np.abs(np.nan_to_num(a_) - np.nan_to_num(b_)) <= 10 ** -casas / 2 + 1e-9)))
checar("clima: IC máximo, IC médio, temperatura média do ar e horas com IC ≥ 36 °C do painel iguais ao CSV",
       igual(J["cl"]["hi_max"], C.hi_max, 1) and igual(J["cl"]["hi_med"], C.hi_med, 2) and igual(J["cl"]["t_med"], C.t_med, 2) and igual(J["cl"]["h36"], C.num_hr_36, 0))

# Nível de Calor reconstruído (4 h com IC ≥ 36: NC 2 em 1 ou 2 dias, NC 3 em 3 dias ou mais; NC 4 com 4 h ≥ 40 e NC 5 com 2 h ≥ 44, dentro de sequência de NC 3)
z = lambda s: s.fillna(0).to_numpy()
aa, bb, cc = z(C.num_hr_36) >= 4, z(C.num_hr_40) >= 4, z(C.num_hr_44) >= 2
seq3 = np.zeros(nd, bool); i = 0
while i < nd:
    if aa[i]:
        j = i
        while j + 1 < nd and aa[j + 1]: j += 1
        if j - i + 1 >= 3: seq3[i:j + 1] = True
        i = j + 1
    else: i += 1
nc = np.ones(nd, int); nc[aa] = 2; nc[seq3] = 3; nc[seq3 & bb] = 4; nc[seq3 & cc] = 5
nc_pn = [None if s else int(v) for v, s in zip(nc, C.num_hr_36.isna().to_numpy())]
checar("Nível de Calor estimado retrospectivamente: NC 1 a NC 5 iguais aos recalculados a partir das horas de IC", nc_pn == J["cl"]["nc"], sum(1 for p, q in zip(nc_pn, J["cl"]["nc"]) if p != q))

# ---------------------------------------------------------------- séries diárias e semanais de todos os recortes
checar("recortes: o painel traz os 87 recortes elegíveis, sem repetição", len(set(J["k"])) == len(J["k"]) and set(J["k"]) <= set(S), set(J["k"]) - set(S))
fit = ~sem_registro & ~nc_dia & ~np.array([sem_clima[max(0, t - 10):t + 1].any() for t in range(nd)])      # ajuste principal: sem registro, mês não consolidado, dia sem clima e os 10 seguintes
dif = [k for k, o in zip(J["k"], J["o"]) if not np.array_equal(np.array(o), S[k])]
checar(f"recortes: a série diária de cada um dos {len(J['k'])} recortes do painel é igual à recalculada dos dados brutos", not dif, dif[:5])
elig = {k for k, v in S.items() if v[fit].sum() >= M["min_obitos"]}
checar(f"recortes: os recortes elegíveis (pelo menos {M['min_obitos']} óbitos nos dias do ajuste) são exatamente os do painel", elig == set(J["k"]), (sorted(elig - set(J["k"]))[:5], sorted(set(J["k"]) - elig)[:5]))
ini = pd.to_datetime(J["sem"]["ini"]); pos = {d: i for i, d in enumerate(dias)}
dsem = [k for k in J["k"] if not np.array_equal(np.array(J["So"][k]), np.array([S[k][pos[d]:pos[d] + 7].sum() for d in ini]))]
checar("recortes: o total semanal (domingo a sábado, semanas completas) de cada recorte é igual ao recalculado", not dsem, dsem[:5])
ok_sem = all((ini[i + 1] - ini[i]).days == 7 for i in range(len(ini) - 1)) and ini[0].dayofweek == 6
checar("datas: as semanas do painel começam no domingo e são consecutivas", ok_sem)
soma_locais = sum(S[f"{L}|Todas as idades"] for L in LOCAIS)
checar("denominadores: a soma dos sete locais do óbito é a série de todos os locais", np.array_equal(soma_locais, S["Todos os locais|Todas as idades"]))
soma_faixas = sum(S[f"Todos os locais|{fx}"] for fx in FAIXAS)
checar("denominadores: a soma das faixas etárias mais os óbitos sem idade é a série de todas as idades", int(soma_faixas.sum()) + int(N.faixa.isna().sum()) == int(S["Todos os locais|Todas as idades"].sum()))
checar("denominadores: a soma diária das séries de causas naturais é o n_obitos do painel", int(S["Todos os locais|Todas as idades"].sum()) == M["n_obitos"])

# ---------------------------------------------------------------- lista de causas (aba Causas específicas)
if a.cidlista:
    CID_MIN = 1500
    sel = {"naturais": P[P.grupo == "natural"], "externas": P[P.grupo == "externa"], "todas_sem_covid": P[P.grupo != "covid"], "todas": P}
    for causa, df in sel.items():
        f = os.path.join(a.cidlista, f"cid_{causa}.json")
        if not os.path.exists(f): print(f"PULADO: {f} não existe"); continue
        L = json.load(open(f, encoding="utf-8"))
        v = df.dia.map(idx); ok = v.notna(); v = v[ok].astype(int)
        cont = df.cid3[ok][fit[v.to_numpy()]].value_counts(); cont = cont[cont >= CID_MIN]
        esp = {k: int(n) for k, n in cont.items()}; got = dict(zip(L["cid"], L["n"]))
        checar(f"CID ({causa}): as causas com pelo menos {CID_MIN} óbitos nos dias do ajuste e o número de óbitos de cada uma são os recalculados dos códigos brutos", esp == got and L["n_dias_ajuste"] == int(fit.sum()), ({k: (esp.get(k), got.get(k)) for k in set(esp) | set(got) if esp.get(k) != got.get(k)}, L["n_dias_ajuste"], int(fit.sum())))

# ---------------------------------------------------------------- tabelas
if a.saida:
    mil = lambda n: f"{int(n):,}".replace(",", ".")
    anos = N.dia.dt.year.value_counts().sort_index()
    md = ["# Conferência independente dos dados", "",
          f"Gerado por `testes/conferir_independente.py` a partir do Parquet do SIM e do CSV do clima, sem usar o código do painel. População: {a.pop}. Série de {INICIO.date():%d/%m/%Y} a {FIM.date():%d/%m/%Y} ({mil(nd)} dias).", "",
          "## Óbitos por grupo de causa básica", "", "| Grupo | Óbitos (recalculado) | Óbitos (painel) |", "|:--|--:|--:|"]
    for g in rec["grupos"]: md.append(f"| {g['rotulo']} | {mil((P.grupo == g['grupo']).sum())} | {mil(g['n'])} |")
    md += [f"| **Total** | **{mil(tot)}** | **{mil(rec['total'])}** |", "", "## Dias fora do ajuste principal", "",
           "| Motivo | Dias |", "|:--|--:|", f"| Sem registro no SIM | {mil(sem_registro.sum())} |", f"| Mês de registro não consolidado ({', '.join(mnc)}) | {mil(nc_dia.sum())} |",
           f"| Sem dado de clima | {mil(sem_clima.sum())} |", f"| No ajuste principal | {mil(fit.sum())} |", "", "## Óbitos por causas naturais, por ano", "", "| Ano | Óbitos |", "|:--|--:|"]
    md += [f"| {y} | {mil(n)} |" for y, n in anos.items()]
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    open(a.saida, "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("gravado:", a.saida)

print("\nFALHAS:", "nenhuma" if not falhas else falhas)
sys.exit(1 if falhas else 0)
