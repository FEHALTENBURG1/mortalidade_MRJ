import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd
import anomalia_clima as ac
import os
clima=pd.read_csv("heat/data/temp_df.csv",parse_dates=["dia"]).sort_values("dia")
resumos={}; an=pd.DataFrame({"dia":clima["dia"]}).set_index("dia")
for v in ["t_med","hi_med"]:
    ok=clima[v].notna().to_numpy(); cv=clima[ok]
    o,r=ac.ajustar_serie(cv["dia"],cv[v].to_numpy(float),"monotonica",12,8)
    for c in ["observado","esperado","desvio_padrao","anomalia","z"]: an[f"{v}_{c}"]=pd.Series(o[c].values,index=cv["dia"].values)
    resumos[v]=r
an=an.reset_index()
pd.DataFrame(resumos).T.to_csv("analise/resumo_gam.csv")
print(pd.DataFrame(resumos).T[["tendencia_c_por_decada","ic95_inf_c_por_decada","ic95_sup_c_por_decada","rho_lag1","dp_medio_c"]])
an.to_csv("analise/anomalias_diarias.csv",index=False)
print("dias z>=1,96 (t_med):",int((an.t_med_z>=1.96).sum()),"| hi_max>=36:",int((clima.hi_max>=36).sum()))
