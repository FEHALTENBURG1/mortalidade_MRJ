"""Valida o núcleo de cálculo contra o statsmodels (RR, EP de quase-Poisson e EP robusto HAC). Rodar dentro da pasta de trabalho do pipeline
(trabalho_painel), depois de painel_pipeline.py: python teste_nucleo.py. Requer statsmodels."""
import sys, os, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd, statsmodels.api as sm, nucleo as nu, time
d=nu.carregar_obitos("silver_user/silver")
cl=pd.read_csv("heat/data/temp_df.csv",parse_dates=["dia"]); an=pd.read_csv("analise/anomalias_diarias.csv",parse_dates=["dia"])
fim,ruins,_=nu.definir_periodo(d,cl.dia.max()); print("fim",fim.date(),[str(p) for p in ruins])
dias=pd.date_range(nu.INICIO,fim)
C=nu.Clima(dias,cl,an); A=nu.Analise(dias,ruins,C)
print("mascara Sem COVID: dias",int(A.mask["Sem COVID"].sum()),"de",len(dias),"| sem_clima",int(C.sem_clima.sum()))
r=d[d.residente&d.cid.map(nu.eh_natural)&(d.dia>=nu.INICIO)&(d.dia<=fim)]
y=r.groupby("dia").size().reindex(dias,fill_value=0).to_numpy(float)
X=nu.exposicoes(C.evento[nu.NOME_ABS])["dia"]
t0=time.time(); f=nu.ajustar_dia(y,X,A,"Sem COVID"); print("tempo",round(time.time()-t0,3))
rr,lo,hi,p=nu.ic(f["est"],f["se"]); print("nucleo   RR=%.4f (%.4f–%.4f) phi=%.2f  EP_hac=%.5f EP_qp=%.5f"%(rr[0],lo[0],hi[0],f["phi"],f["se"][0],f["se_qp"][0]))
# statsmodels com a mesma matriz
m=A.mask["Sem COVID"]; Cm=A.controles("Sem COVID"); XX=np.column_stack([X.to_numpy()[m],Cm])
g=sm.GLM(y[m],XX,family=sm.families.Poisson()).fit(scale="X2")
print("statsm.  RR=%.4f EP_qp=%.5f phi=%.2f"%(np.exp(g.params[0]),g.bse[0],g.scale))
h=sm.GLM(y[m],XX,family=sm.families.Poisson()).fit(cov_type="HAC",cov_kwds={"maxlags":14,"use_correction":True})
print("statsm. HAC14  EP=%.5f (nucleo %.5f)"%(h.bse[0],f["se"][0]))
# no grid de tempo completo (statsmodels HAC trata linhas como consecutivas; nosso usa posições reais)
print("n obs",m.sum(),"p",XX.shape[1])

# ---------------------------------------------------------------- janelas de anos
y0, y1 = int(dias[0].year), int(dias[-1].year)
mj = A.mascara("Sem COVID", y0, y1)
assert (mj == A.mask["Sem COVID"]).all(), "janela da série inteira deve ter a mesma máscara do recorte"
fj = nu.ajustar_dia(y, X, A, "Sem COVID", mask=mj)
assert np.allclose(fj["est"], f["est"], rtol=1e-8, atol=1e-10) and np.allclose(fj["se"], f["se"], rtol=1e-8, atol=1e-10), "janela inteira deve reproduzir o ajuste-base"
print("janela inteira %d-%d: reproduz o ajuste-base (RR %.4f)" % (y0, y1, np.exp(fj["est"][0])))
a, b = y0 + 3, y1 - 1                                                   # janela parcial: refaz spline e EP só com os dias da janela
mw = A.mascara("Sem COVID", a, b); assert nu.MIN_DIAS_JANELA <= mw.sum() < mj.sum()
assert not mw[~np.asarray((dias >= f"{a}-01-01") & (dias <= f"{b}-12-31"))].any()
fw = nu.ajustar_dia(y, X, A, "Sem COVID", mask=mw)
Cw = nu.controles_diarios(dias, mw, A.df_ano)[0]; XXw = np.column_stack([X.to_numpy()[mw], Cw])
hw = sm.GLM(y[mw], XXw, family=sm.families.Poisson()).fit(cov_type="HAC", cov_kwds={"maxlags": 14, "use_correction": True})
print("janela %d-%d: nucleo RR=%.4f EP=%.5f | statsmodels RR=%.4f EP=%.5f" % (a, b, np.exp(fw["est"][0]), fw["se"][0], np.exp(hw.params[0]), hw.bse[0]))
assert abs(np.exp(fw["est"][0]) - np.exp(hw.params[0])) < 1e-4 and abs(fw["se"][0] / hw.bse[0] - 1) < 0.02
grade = A.janelas(); assert all(g["y0"] <= g["y1"] for g in grade) and all(max(g["dias"].values()) >= nu.MIN_DIAS_JANELA for g in grade)
print("grade de janelas:", len(grade))

# ---------------------------------------------------------------- Níveis de Calor (protocolo): casos construídos à mão
h36 = [0, 5, 0, 4, 6, 7, 5, 0, 2, 4, 4, np.nan, 5, 5, 5]
h40 = [0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0]
h44 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0]
t = pd.DataFrame({"num_hr_36": h36, "num_hr_40": h40, "num_hr_44": h44})
nc = nu.nivel_calor(t)
esperado = [1, 2, 1, 3, 3, 4, 3, 1, 1, 2, 2, np.nan, 3, 5, 3]
assert np.array_equal(np.nan_to_num(nc, nan=-1), np.nan_to_num(np.array(esperado, float), nan=-1)), (nc, esperado)
print("nivel_calor: casos construídos conferem")

# ---------------------------------------------------------------- esperado diário (escala diária da Figura 1)
f0 = nu.ajuste_diario(y, A); mu = f0["mu"]; m0 = A.mask["Sem COVID"]
assert np.isnan(mu[A.inc | A.covid]).all() and not np.isnan(mu[m0]).any(), "esperado só vazio nos dias de COVID e de mês incompleto"
assert abs(mu[m0].sum() / y[m0].sum() - 1) < 1e-6, "Poisson com constante: soma dos esperados = soma dos observados nos dias do ajuste"
g2 = sm.GLM(y[m0], np.column_stack([A.controles("Sem COVID")]), family=sm.families.Poisson()).fit(scale="X2")
assert np.allclose(g2.fittedvalues, mu[m0], rtol=1e-5) and abs(g2.scale - f0["phi"]) < 1e-3, "esperado diário sem calor coincide com o statsmodels"
# com calor em t a t-3: observado ÷ esperado nos dias expostos = RR do modelo; nos demais = 1 (equações de escore)
fx = nu.ajuste_diario(y, A, X=X.iloc[:, 0].to_numpy(float)); xe = X.iloc[:, 0].to_numpy(float) > 0
assert abs(y[m0 & xe].sum() / fx["mu"][m0 & xe].sum() - fx["rr"]) < 1e-6 and abs(y[m0 & ~xe].sum() / fx["mu"][m0 & ~xe].sum() - 1) < 1e-6
assert abs(fx["rr"] - np.exp(f["est"][0])) < 1e-9, "RR do modelo da Figura 1 coincide com o do ajustar_dia na mesma máscara"
print("esperado diário: confere com o statsmodels (phi %.2f); com calor lag 0-3: RR %.4f = O/E dos expostos" % (f0["phi"], fx["rr"]))

# ---------------------------------------------------------------- contraste entre locais do óbito (domicílio x hospital)
# O contraste beta_domicílio - beta_hospital, com EP HAC da série de influência combinada (nu.combinar), deve coincidir com o modelo empilhado
# do statsmodels (parâmetros de controle próprios de cada local; escores somados por dia antes do HAC: cov_type='hac-groupsum').
loc = nu.classificar_local(r, nu.tabela_cnes("analise/cnes_estab.csv"))
yh = r[loc == "Hospital"].groupby("dia").size().reindex(dias, fill_value=0).to_numpy(float)
yd = r[loc == "Domicílio"].groupby("dia").size().reindex(dias, fill_value=0).to_numpy(float)
fh, fd = nu.ajustar_dia(yh, X, A, "Sem COVID"), nu.ajustar_dia(yd, X, A, "Sem COVID")
est, se, rr_, lo_, hi_, p_ = nu.combinar([(fd, 0), (fh, 0)], [1, -1])
n_ = int(m.sum()); Z = np.zeros_like(Cm); xe_ = X.to_numpy()[m]
big = np.vstack([np.column_stack([np.zeros_like(xe_), xe_, Cm * 0, Cm]), np.column_stack([xe_, np.zeros_like(xe_), Cm, Cm * 0])])  # [beta_H, beta_D, ctrl_H, ctrl_D]
yy = np.r_[yd[m], yh[m]]; big = np.vstack([np.column_stack([np.zeros_like(xe_), xe_, Cm * 0, Cm]), np.column_stack([xe_, np.zeros_like(xe_), Cm, Cm * 0])])
tt = np.r_[np.arange(n_), np.arange(n_)]
gs = sm.GLM(yy, big, family=sm.families.Poisson()).fit(cov_type="hac-groupsum", cov_kwds={"time": tt, "maxlags": 14, "use_correction": True})
cd = np.zeros(big.shape[1]); cd[1], cd[0] = 1, -1
est_sm = float(cd @ gs.params); se_sm = float(np.sqrt(cd @ gs.cov_params() @ cd))
print("domicílio/hospital: nucleo razão de RR=%.4f (EP log %.5f) | statsmodels empilhado %.4f (EP %.5f)" % (np.exp(est), se, np.exp(est_sm), se_sm))
assert abs(est - est_sm) < 1e-4, "razão de RR deve coincidir com o modelo empilhado"
assert abs(se / se_sm - 1) < 0.05, "EP do contraste deve coincidir (±5%) com o modelo empilhado com hac-groupsum"
st, df_, pw = nu.wald_homog([(fh, 0), (fd, 0)]); z_ = est / se
assert abs(st - z_ ** 2) < 1e-6 and df_ == 1, "Wald de 2 grupos = quadrado do z do contraste"
print("Wald de igualdade (2 locais) = z² do contraste: ok")

# ---- raça/cor: classificação do RACACOR e agregado PPI
r_ = nu.classificar_raca(pd.Series(["1", "2", "3", "4", "5", "9", None, "1.0", " 4"]))
assert list(r_) == ["Branca", "Preta", "Amarela", "Parda", "Indígena", "Ignorada", "Ignorada", "Branca", "Parda"], "classificação do RACACOR"
dd_ = d[d.dia >= "2012-01-01"]; ntot = len(dd_)
assert dd_.raca.isin(["Branca", "Preta", "Amarela", "Parda", "Indígena", "Ignorada"]).all() and dd_.raca.notna().all()
Yr = nu.series_local_raca(dd_.assign(natural=True, local="Hospital"), pd.date_range("2012-01-01", d.dia.max()), locais=["Hospital"])
ppi_ = int(Yr[("Todos os locais", "Todas as idades|PPI")].sum()); br_ = int(Yr[("Todos os locais", "Todas as idades|Branca")].sum())
assert ppi_ == int(dd_.raca.isin(nu.PPI).sum()) and br_ == int((dd_.raca == "Branca").sum()), "séries por raça/cor e agregado PPI"
print("raça/cor: classificação e PPI (preta + parda + indígena) conferem; PPI = %.1f%% e branca = %.1f%% dos óbitos desde 2012" % (100 * ppi_ / ntot, 100 * br_ / ntot))
