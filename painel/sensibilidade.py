"""Números que sustentam a aba Métodos: fluxo de dados, exemplo de cálculo passo a passo, diagnóstico dos resíduos, tabela de sensibilidade e
efeito por estação do ano. Usa residentes que morreram no Rio, causas naturais, todos os locais e idades. Uso: python sensibilidade.py"""
import sys, os, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, nucleo as nu
from scipy.stats import chi2
A_ = "analise/"
cx = nu.contexto("res"); d = cx.d; dias, An, C = cx.dias, cx.A, cx.clima
y_nat = nu.serie_dias(d[d.natural], dias); y_sens = nu.serie_dias(d[d.natural & d.sensivel], dias)
y_tod = nu.serie_dias(d[~d.covid], dias); y_ext = nu.serie_dias(d[~d.natural & ~d.covid], dias)
y_nat_cov = nu.serie_dias(d[d.natural | d.covid], dias)   # naturais + COVID (B34), para mostrar o efeito de manter a COVID no desfecho
out = {}

# ---------- fluxo de dados
da = cx.d_all; da = da[(da.dia >= nu.INICIO) & (da.dia <= cx.fim)]
dr = da[da.residente]
base = An.mask["Sem COVID"]
out["fluxo"] = dict(
    periodo=[str(dias[0].date()), str(cx.fim.date())], n_dias=len(dias),
    obitos_ocorridos=int(len(da)), obitos_residentes=int(len(dr)), obitos_res_naturais=int(dr.cid.map(nu.eh_natural).sum()),
    obitos_res_externos=int((~dr.cid.map(nu.eh_natural) & ~dr.cid.map(nu.eh_covid)).sum()), obitos_res_covid=int(dr.cid.map(nu.eh_covid).sum()),
    obitos_res_covid_fora_janela=int(dr[~dr.dia.between(*[pd.Timestamp(x) for x in nu.COVID])].cid.map(nu.eh_covid).sum()),
    obitos_nao_res_naturais=int(da[~da.residente].cid.map(nu.eh_natural).sum()),
    dias_covid=int(An.covid.sum()), dias_incompletos=int(An.inc.sum()), dias_sem_clima=int(C.sem_clima.sum()),
    dias_modelo_sem_covid=int(base.sum()), dias_modelo_todo=int(An.mask["Todo o período"].sum()),
    obitos_modelo_sem_covid=int(y_nat[base].sum()), meses_fora=[str(p) for p in cx.ruins], covid=list(nu.COVID))

# ---------- exemplo numérico passo a passo
ex = {}
for dn in nu.DEFS:
    X = nu.exposicoes(C.evento[dn])["dia"]; f = nu.ajustar_dia(y_nat, X, An, "Sem COVID"); m = An.mask["Sem COVID"]
    b = float(f["est"][0]); x = X.iloc[:, 0].to_numpy()[m] > 0; yy = y_nat[m]; mu = f["mu"]; mu0 = mu[x] / np.exp(b)
    ex[dn] = dict(n_dias=int(m.sum()), dias_expostos=int(x.sum()), pct_expostos=round(100 * float(x.mean()), 1), obitos_totais=int(yy.sum()), obs_expostos=int(yy[x].sum()),
                  esp_sem_exposicao=round(float(mu0.sum()), 1), obs_esp=round(float(yy[x].sum() / mu0.sum()), 4), beta=round(b, 5), ep_hac=round(float(f["se"][0]), 5), ep_qp=round(float(f["se_qp"][0]), 5),
                  phi=round(float(f["phi"]), 3), rr=round(float(np.exp(b)), 4), lo=round(float(np.exp(b - 1.96 * f["se"][0])), 4), hi=round(float(np.exp(b + 1.96 * f["se"][0])), 4),
                  p=float(nu.ic(f["est"], f["se"])[3][0]), n_param=int(f["p"]), df_tempo=int(f["p"] - 7 + 1 - 1))
out["exemplo"] = ex

# ---------- diagnóstico dos resíduos
def diag(df_ano, dn=nu.NOME_ABS):
    X = nu.exposicoes(C.evento[dn])["dia"]; f = nu.ajustar_dia(y_nat, X, An, "Sem COVID", df_ano=df_ano); m = An.mask["Sem COVID"]
    r = pd.Series((y_nat[m] - f["mu"]) / np.sqrt(f["mu"])); n = len(r)
    ac = [float(r.autocorr(k)) for k in range(1, 15)]
    Q = n * (n + 2) * sum(ac[k - 1] ** 2 / (n - k) for k in range(1, 15)); pLB = float(chi2.sf(Q, 14))
    return dict(df_ano=df_ano, phi=round(float(f["phi"]), 3), acf1=round(ac[0], 3), acf7=round(ac[6], 3), acf14=round(ac[13], 3), ljung_box_14_p=pLB,
                ep_qp=round(float(f["se_qp"][0]), 5), ep_hac=round(float(f["se"][0]), 5), razao_ep=round(float(f["se"][0] / f["se_qp"][0]), 2))
out["diag"] = [diag(g) for g in (2, 4, 7, 10)]

# ---------- sensibilidade
rows = []
def add(dn, rotulo, grupo, y, X, per="Sem COVID", df_ano=None, lags=nu.HAC_LAGS, mask=None, coluna=0):
    f = nu.ajustar_dia(y, X, An, per, df_ano=df_ano, lags=lags, mask=mask); rr, lo, hi, p = nu.ic(f["est"], f["se"]); m = An.mask[per] if mask is None else mask
    rows.append(dict(definicao=dn, grupo=grupo, spec=rotulo, rr=round(float(rr[coluna]), 4), lo=round(float(lo[coluna]), 4), hi=round(float(hi[coluna]), 4), p=float(p[coluna]),
                     dias_exp=int((X.iloc[:, coluna].to_numpy()[m] > 0).sum()), obitos=int(y[m].sum())))
anos = np.asarray(dias.year)
for dn in nu.DEFS:
    ev = C.evento[dn]; X = nu.exposicoes(ev)["dia"]
    add(dn, "Modelo principal", "Principal", y_nat, X)
    add(dn, "Erro-padrão de quase-Poisson (sem correção de autocorrelação)", "Incerteza", y_nat, X, lags=0)
    for g in (2, 4, 10): add(dn, f"{g} graus de liberdade por ano para tendência e sazonalidade", "Controle de tempo", y_nat, X, df_ano=g)
    for k, nome in ((1, "Janela só do dia (lag 0)"), (2, "Janela lag 0–1"), (7, "Janela lag 0–6")):
        add(dn, nome, "Janela de exposição", y_nat, nu.exposicoes(ev, k)["dia"])
    add(dn, "Inclui o período COVID (mar/2020–jun/2022)", "Período", y_nat, X, per="Todo o período")
    add(dn, "Somente 2012–2019 (antes da COVID)", "Período", y_nat, X, mask=base & (anos <= 2019))
    add(dn, "Sem 2022 (rede com poucas estações no clima)", "Dados de clima", y_nat, X, mask=base & (anos != 2022))
    add(dn, "Somente 2014 em diante (rede com 8 ou mais estações)", "Dados de clima", y_nat, X, mask=base & (anos >= 2014))
    add(dn, "Desfecho: causas sensíveis ao calor (lista a priori)", "Desfecho", y_sens, X)
    add(dn, "Desfecho: todas as causas, exceto COVID (inclui externas)", "Desfecho", y_tod, X)
    add(dn, "Desfecho: causas naturais mantendo os óbitos por COVID (B34)", "Desfecho", y_nat_cov, X)
    add(dn, "Desfecho: causas naturais mantendo COVID, período todo", "Período", y_nat_cov, X, per="Todo o período")
    add(dn, "Desfecho: somente causas externas (V–Y)", "Desfecho", y_ext, X)
    # estratos ano-mês + dia da semana (efeitos fixos) em vez de spline
    ym = pd.Series(dias.year * 100 + dias.month)[base].to_numpy(); S = pd.get_dummies(ym).to_numpy(float)
    dow = np.eye(7)[np.asarray(dias.dayofweek)][:, 1:][base]
    f = nu.poisson_fit(y_nat[base], np.column_stack([X.to_numpy()[base], S, dow]), 1, lags=0); rr, lo, hi, p = nu.ic(f["est"], f["se"])
    rows.append(dict(definicao=dn, grupo="Desenho", spec="Efeitos fixos de ano-mês e dia da semana (no lugar do spline)", rr=round(float(rr[0]), 4), lo=round(float(lo[0]), 4), hi=round(float(hi[0]), 4),
                     p=float(p[0]), dias_exp=int(X.iloc[:, 0].to_numpy()[base].sum()), obitos=int(y_nat[base].sum())))
out["sens"] = rows

# ---------- efeito por estação (verão: dez-mar)
saz = []
verao = np.isin(dias.month, [12, 1, 2, 3])
for dn in nu.DEFS:
    ae = nu.exposicoes(C.evento[dn])["dia"].iloc[:, 0].to_numpy()
    X = pd.DataFrame({"Dez–mar": ae * verao, "Abr–nov": ae * ~verao}); f = nu.ajustar_dia(y_nat, X, An, "Sem COVID"); rr, lo, hi, p = nu.ic(f["est"], f["se"]); m = An.mask["Sem COVID"]
    for j, k in enumerate(X.columns):
        saz.append(dict(definicao=dn, estacao=k, rr=round(float(rr[j]), 4), lo=round(float(lo[j]), 4), hi=round(float(hi[j]), 4), dias_exp=int((X[k].to_numpy()[m] > 0).sum())))
out["sazonal"] = saz
# teste de interação: coluna 2 = (exposição × dez–mar) é a diferença em log-RR entre dez–mar e abr–nov; p vem do erro-padrão robusto dessa coluna
inter = []
for dn in nu.DEFS:
    ae = nu.exposicoes(C.evento[dn])["dia"].iloc[:, 0].to_numpy()
    X = pd.DataFrame({"expo": ae, "expo_x_verao": ae * verao}); f = nu.ajustar_dia(y_nat, X, An, "Sem COVID"); rr, lo, hi, p = nu.ic(f["est"], f["se"])
    inter.append(dict(definicao=dn, razao=round(float(rr[1]), 4), lo=round(float(lo[1]), 4), hi=round(float(hi[1]), 4), p=float(p[1])))
out["sazonal_interacao"] = inter
json.dump(out, open(A_ + "metodos_numeros.json", "w"), ensure_ascii=False, indent=1)
print("ok", len(rows), "especificações")
