"""
Núcleo de cálculo do painel mortalidade x calor (MRJ).

Tudo que define "como o número foi calculado" está neste arquivo; os demais scripts só pedem estimativas.

Desenho: série temporal ecológica diária. Desfecho = óbitos por dia (SIM, município do Rio de Janeiro).
Exposição = indicador de dia de calor em t, t-1, t-2 ou t-3 (janela de 4 dias).
Modelo: regressão de Poisson de quase-verossimilhança (log-link)

    log E[Y_t] = spline_natural(t; 7 gl por ano observado) + dia_da_semana + beta * exposicao_t

RR = exp(beta). IC 95% = exp(beta +- 1,96 EP), com EP robusto à autocorrelação e à superdispersão
(estimador de Newey-West, núcleo de Bartlett, 14 defasagens). O EP de quase-Poisson (escala de Pearson) é guardado
junto para comparação.

Dias fora da análise (peso zero, linha removida do ajuste): período COVID (apenas no recorte "Sem COVID"), meses com
registro incompleto no SIM e dias sem clima (e os 3 seguintes, cuja janela os contém).
"""
from __future__ import annotations
import glob, hashlib
from pathlib import Path
import numpy as np, pandas as pd
from patsy import dmatrix, build_design_matrices
from scipy.stats import norm

INICIO = "2012-01-01"
INICIO_SERIE = "2006-01-01"   # início das séries de mortalidade da Figura 1 (o SIM do data lake começa em 2006 e o clima em abril de 2007); os modelos de RR começam em INICIO
COVID = ("2020-03-01", "2022-06-30")
DF_ANO = 7            # graus de liberdade do spline de tempo por ano de dados observados
JANELA = 4            # exposição = dia extremo em t, t-1, t-2 ou t-3
HAC_LAGS = 14
MIN_DIAS_EXPOSTOS = 15
LIM_Z, LIM_HI = 1.96, 36.0
LIMIAR_MES = 0.80     # mês com taxa diária < 80% da mediana dos 12 meses completos anteriores = incompleto
MIN_DIAS_JANELA = 1000   # janela de anos escolhida pelo usuário: mínimo de dias no ajuste (cerca de 2,7 anos); abaixo disso a janela não é estimada

NOME_ANOM = "Anomalia térmica (z ≥ 1,96 na temperatura média)"
NOME_ABS = "Calor intenso (índice de calor máx. ≥ 36 °C)"
DEFS = [NOME_ANOM, NOME_ABS]
PERIODOS = ["Sem COVID", "Todo o período"]
LOCAIS = ["Hospital", "UPA / pronto atendimento", "Outros estabelecimentos de saúde", "Domicílio", "Via pública", "Outros locais", "Ignorado"]
FAIXAS = ["<1 ano", "1 ano", "2–5", "6–10", "11–20", "21–30", "31–40", "41–50", "51–60", "61–70", "71–80", "81+"]
_BINS = [-np.inf, 1, 2, 6, 11, 21, 31, 41, 51, 61, 71, 81, np.inf]

# ---------------------------------------------------------------- causas
NATURAIS = set("ABCDEFGHIJKLMNOPQR")          # capítulos A00–R99, menos a COVID-19 (ver eh_covid); exclui causas externas V–Y
INCLUIR_CAPS = set("ABEFGIJN")                # lista a priori de causas sensíveis ao calor (desfecho secundário)
INCLUIR_FAIXAS = [("R", 95, 99), ("X", 30, 30), ("W", 65, 74)]

def eh_covid(c) -> bool:
    """COVID-19. No silver o SIM codifica B34.2 (coronavírus, localização não especificada); com a causa truncada em 3 caracteres
    isso vira 'B34'. Antes de 2020 há ~16 óbitos B34 em 8 anos (infecção viral não especificada), então o grupo é praticamente só COVID.
    Códigos U (U07.x) também entram, caso apareçam em versões futuras do silver."""
    c = str(c).strip().upper()
    return c[:3] == "B34" or c[:1] == "U"

def eh_natural(c) -> bool:
    c = str(c).strip().upper()
    return len(c) >= 3 and c[0] in NATURAIS and not eh_covid(c)

def influenciado(c) -> bool:
    c = str(c).strip().upper()
    if len(c) < 3 or not c[0].isalpha(): return False
    if c[0] in INCLUIR_CAPS: return True
    try: n = int(c[1:3])
    except ValueError: return False
    return any(c[0] == l and a <= n <= b for l, a, b in INCLUIR_FAIXAS)

# ---------------------------------------------------------------- dados
def carregar_obitos(silver) -> pd.DataFrame:
    """Todos os óbitos ocorridos no MRJ (residentes ou não), todos os anos do silver."""
    fs = sorted(glob.glob(str(Path(silver) / "sim/ocorrencia_mrj/ano_arquivo=20*/part-0.parquet")))
    cols = ["DTOBITO", "idade_anos", "CAUSABAS", "LOCOCOR", "CODESTAB", "ocorrencia_mrj", "residente_mrj"]
    d = pd.concat([pd.read_parquet(f, columns=cols) for f in fs], ignore_index=True)
    d = d[d.ocorrencia_mrj == True].copy()
    d["dia"] = pd.to_datetime(d.DTOBITO).dt.normalize()
    d["cid"] = d.CAUSABAS.astype(str).str.strip().str.upper().str[:3]
    d["residente"] = d.residente_mrj == True
    d["CODESTAB"] = cnes7(d.CODESTAB)
    return d[["dia", "idade_anos", "cid", "LOCOCOR", "CODESTAB", "residente"]]

def meses_incompletos(d: pd.DataFrame, limiar: float = LIMIAR_MES, inicio: str = INICIO):
    """Marca meses com registro incompleto no SIM. Devolve (contagem mensal, Series booleana por mês).
    Compara a taxa diária do mês com a mediana das taxas dos 12 últimos meses COMPLETOS; mês ausente conta como incompleto."""
    m = d.dia.dt.to_period("M").value_counts().sort_index()
    m = m[m.index >= pd.Period(inicio[:7])]
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0)
    taxa = m / m.index.days_in_month
    boas, ruim = [], {}
    cov0, cov1 = pd.Period(COVID[0][:7]), pd.Period(COVID[1][:7])
    for per, t in taxa.items():
        em_covid = cov0 <= per <= cov1          # meses de COVID têm taxa inflada: não servem de referência nem são marcados
        if len(boas) >= 12 and not em_covid:
            ref = np.median(boas[-12:]); ruim[per] = bool(t < limiar * ref)
        else:
            ruim[per] = False
        if not ruim[per] and not em_covid: boas.append(t)
    return m, pd.Series(ruim)

def definir_periodo(d: pd.DataFrame, ultimo_dia_clima: pd.Timestamp, inicio: str = INICIO):
    """Fim da janela = último dia com clima e último mês completo do SIM (o último mês observado é descartado se não termina em
    seu último dia ou se está incompleto). Meses incompletos no meio da série são mascarados, não cortados."""
    m, ruim = meses_incompletos(d, inicio=inicio)
    ultimo = m.index[-1]
    fim_obs = d.dia.max()
    if fim_obs < ultimo.to_timestamp(how="end").normalize(): ultimo = ultimo - 1
    while ultimo in ruim.index and ruim[ultimo]: ultimo = ultimo - 1
    fim = min(ultimo.to_timestamp(how="end").normalize(), pd.Timestamp(ultimo_dia_clima))
    ruins = [p for p, r in ruim.items() if r and p.to_timestamp() <= fim]
    return fim, ruins, m

def cnes7(s: pd.Series) -> pd.Series:
    """Código CNES com 7 dígitos (zeros à esquerda restaurados: planilhas e leitores de CSV os perdem)."""
    return s.astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(7)

def tabela_cnes(caminho) -> pd.DataFrame:
    t = pd.read_csv(caminho, dtype=str)
    t["CODESTAB"] = cnes7(t.CODESTAB)
    if "tipo" in t: t["tipo"] = pd.to_numeric(t.tipo, errors="coerce")
    return t.drop_duplicates("CODESTAB")

def classificar_local(d: pd.DataFrame, tipo_cnes: pd.DataFrame) -> pd.Series:
    """Local do óbito: LOCOCOR do SIM refinado pelo tipo do estabelecimento no CNES (pronto-socorro/UPA x hospital)."""
    t = tipo_cnes.set_index("CODESTAB").tipo
    tipo = d.CODESTAB.map(t)
    l = d.LOCOCOR.astype("string")
    out = pd.Series("Outros estabelecimentos de saúde", index=d.index, dtype=object)
    hosp = tipo.isin([5, 7, 15, 62]); upa = tipo.isin([20, 21, 73]); sem = tipo.isna()
    out[hosp] = "Hospital"; out[upa] = "UPA / pronto atendimento"
    out[sem & (l == "1")] = "Hospital"
    out[l == "3"] = "Domicílio"; out[l == "4"] = "Via pública"; out[l.isin(["5", "6"])] = "Outros locais"
    out[(l == "9") | l.isna()] = "Ignorado"
    return out

def faixa_etaria(idade) -> pd.Series:
    return pd.cut(idade, _BINS, right=False, labels=FAIXAS)

# ---------------------------------------------------------------- clima e exposição
class Clima:
    """Clima diário alinhado a `dias`. `cl` = HAAT (arquivo haat_diario_municipal.csv); `an` = anomalias (anomalia_haat.py)."""
    def __init__(self, dias, cl: pd.DataFrame, an: pd.DataFrame):
        self.dias = dias
        self.cl = cl.set_index("dia").reindex(dias)
        self.an = an.set_index("dia").reindex(dias)
        z = self.an["t_med_z"].to_numpy(float); hi = self.cl["hi_max"].to_numpy(float)
        self.evento = {NOME_ANOM: np.where(np.isnan(z), np.nan, (z >= LIM_Z).astype(float)),
                       NOME_ABS: np.where(np.isnan(hi), np.nan, (hi >= LIM_HI).astype(float))}
        nan = np.isnan(z) | np.isnan(hi)
        self.sem_clima = pd.Series(nan.astype(float)).rolling(JANELA, min_periods=1).max().to_numpy() > 0

def runs(e: np.ndarray, minimo: int = 2) -> np.ndarray:
    s = pd.Series(e.astype(int)); g = (s != s.shift()).cumsum(); n = s.groupby(g).transform("sum")
    return ((s == 1) & (n >= minimo)).to_numpy()

def janela_max(x: np.ndarray, k: int = JANELA) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).fillna(0).rolling(k, min_periods=1).max().to_numpy() > 0

def exposicoes(evento: np.ndarray, k: int = JANELA) -> dict:
    """Esquemas de exposição para uma definição de evento (vetor 0/1/NaN por dia)."""
    e = np.nan_to_num(evento).astype(bool)
    ae = janela_max(e, k); w = runs(e); aw = janela_max(w, k); iso = ae & ~aw
    return {"dia": pd.DataFrame({"Dia de calor (lag 0–3)": ae.astype(float)}),
            "onda": pd.DataFrame({"Dia de calor isolado": iso.astype(float), "Onda de calor (≥2 dias)": aw.astype(float)})}

def nivel_calor(cl: pd.DataFrame) -> np.ndarray:
    """Nível de Calor (NC 1 a 5) de cada dia pelo protocolo da Prefeitura do Rio (Decreto Rio nº 54.740/2024), reconstruído a partir do HAAT.
    Usa as horas do dia com índice de calor (IC) acima de cada limiar (colunas num_hr_36, num_hr_40, num_hr_44; contagem com IC >= limiar).
      a = pelo menos 4 h com IC >= 36 °C;  b = pelo menos 4 h com IC >= 40 °C;  c = pelo menos 2 h com IC >= 44 °C
      NC1: nenhum dos casos abaixo | NC2: a, em sequência de 1 ou 2 dias | NC3: a, em sequência de 3 dias ou mais
      NC4: b dentro de uma sequência de a com 3 dias ou mais | NC5: c dentro de uma sequência de a com 3 dias ou mais.
    Limites desta reconstrução: usa só o observado (o protocolo também admite a previsão dos dois dias seguintes), a série é a média das estações
    do município e o corte é >= (o decreto diz "acima de"). A classificação oficial é a divulgada pelo COR-Rio. Dia sem clima = NaN."""
    h36, h40, h44 = (cl[c].to_numpy(float) for c in ("num_hr_36", "num_hr_40", "num_hr_44"))
    a = np.nan_to_num(h36) >= 4; b = np.nan_to_num(h40) >= 4; c = np.nan_to_num(h44) >= 2
    sq = runs(a, 3); nc = np.ones(len(cl)); nc[a] = 2; nc[sq] = 3; nc[sq & b] = 4; nc[sq & c] = 5
    nc[np.isnan(h36)] = np.nan
    return nc

# ---------------------------------------------------------------- máscaras e controles
class Analise:
    """Contexto de uma análise: dias, máscaras por recorte e matrizes de controle (com cache)."""
    def __init__(self, dias, meses_ruins, clima: Clima, df_ano: int = DF_ANO):
        self.dias = dias; self.clima = clima; self.df_ano = df_ano
        self.inc = np.asarray(pd.PeriodIndex(dias, freq="M").isin(meses_ruins))
        self.covid = np.asarray((dias >= COVID[0]) & (dias <= COVID[1]))
        base = ~(self.inc | clima.sem_clima)
        self.mask = {"Todo o período": base, "Sem COVID": base & ~self.covid}
        self.t = np.arange(len(dias)); self._c = {}; self._cm = {}
    def controles(self, periodo: str, df_ano: int | None = None):
        df_ano = df_ano or self.df_ano; k = (periodo, df_ano)
        if k not in self._c:
            m = self.mask[periodo]; self._c[k] = controles_diarios(self.dias, m, df_ano)[0]
        return self._c[k]
    def mascara(self, periodo: str, y0: int | None = None, y1: int | None = None) -> np.ndarray:
        """Máscara do recorte restrita à janela de anos civis [y0, y1]. Sem anos, devolve a máscara do recorte inteiro."""
        m = self.mask[periodo]
        if y0 is None: return m
        return m & np.asarray((self.dias >= f"{y0}-01-01") & (self.dias <= f"{y1}-12-31"))
    def controles_mascara(self, m: np.ndarray, df_ano: int | None = None):
        """Controles (spline de tempo + dia da semana) para uma máscara qualquer, com cache pequeno (a matriz depende só da máscara)."""
        df_ano = df_ano or self.df_ano; k = (hashlib.md5(np.ascontiguousarray(m).tobytes()).digest(), df_ano)
        if k not in self._cm:
            if len(self._cm) >= 12: self._cm.pop(next(iter(self._cm)))
            self._cm[k] = controles_diarios(self.dias, m, df_ano)[0]
        return self._cm[k]
    def janelas(self, y0_min: int | None = None):
        """Grade de janelas de anos civis (y0, y1) com y0 <= y1 dentro da série. Para cada uma, devolve os dias no ajuste de cada recorte;
        a janela só vale para o recorte com pelo menos MIN_DIAS_JANELA dias."""
        a0 = int(self.dias[0].year) if y0_min is None else y0_min; a1 = int(self.dias[-1].year); g = []
        for y0 in range(a0, a1 + 1):
            for y1 in range(y0, a1 + 1):
                nd = {p: int(self.mascara(p, y0, y1).sum()) for p in PERIODOS}
                if any(v >= MIN_DIAS_JANELA for v in nd.values()): g.append(dict(y0=y0, y1=y1, dias=nd))
        return g

def controles_diarios(dias, m: np.ndarray, df_ano: int):
    t = np.arange(len(dias)); nobs = int(m.sum()); df = max(int(round(nobs / 365.25 * df_ano)), 4)
    dm = dmatrix(f"cr(x, df={df}) - 1", {"x": t[m]}, return_type="dataframe")
    dow = np.eye(7)[np.asarray(dias.dayofweek)][:, 1:][m]
    return np.column_stack([np.asarray(dm), dow]), dm.design_info

def base_prever(di, t_all):
    return np.asarray(build_design_matrices([di], {"x": t_all})[0])

# ---------------------------------------------------------------- ajuste
def poisson_fit(y, X, kexp: int, tpos=None, ntot=None, lags: int = HAC_LAGS, contrastes=None, maxit: int = 40, tol: float = 1e-10):
    """Poisson (log) por IRLS. As `kexp` primeiras colunas de X são as exposições.
    Devolve estimativas (log-RR) dos contrastes pedidos (padrão: cada exposição) com EP robusto (HAC) e de quase-Poisson."""
    y = np.asarray(y, float); X = np.asarray(X, float); n, p = X.shape
    mu = y + 0.5; eta = np.log(mu); dev0 = np.inf
    for _ in range(maxit):
        z = eta + (y - mu) / mu
        XtW = X.T * mu
        M = XtW @ X + 1e-9 * np.eye(p)
        try:
            b = np.linalg.solve(M, XtW @ z)
        except np.linalg.LinAlgError:                    # séries muito esparsas (unidade que abre no meio do período)
            b = np.linalg.lstsq(M, XtW @ z, rcond=1e-12)[0]
        eta = X @ b; mu = np.exp(np.clip(eta, -12, 30))
        with np.errstate(divide="ignore", invalid="ignore"):
            dev = 2 * np.sum(np.where(y > 0, y * np.log(y / mu), 0) - (y - mu))
        if abs(dev - dev0) < tol * (abs(dev) + 0.1): break
        dev0 = dev
    XtW = X.T * mu; bread = np.linalg.pinv(XtW @ X + 1e-9 * np.eye(p), hermitian=True)
    phi = float(np.sum((y - mu) ** 2 / mu) / (n - p))
    K = np.eye(p)[:kexp] if contrastes is None else np.atleast_2d(np.asarray(contrastes, float))
    est = K @ b; V = K @ bread @ K.T
    se_qp = np.sqrt(np.diag(V) * phi)
    se = se_qp.copy(); G = []; corr = n / (n - p)
    if lags:
        res = y - mu; ntot = ntot or n
        for i, c in enumerate(K):
            q = res * (X @ (bread @ c))                      # função de influência do contraste, dia a dia
            if tpos is not None:
                g = np.zeros(ntot); g[tpos] = q
            else:
                g = q
            G.append(g)
            se[i] = np.sqrt(max(hac_soma(g, lags) * corr, 0.0))
    return dict(est=est, se=se, se_qp=se_qp, phi=phi, mu=mu, b=b, n=n, p=p, G=np.array(G), corr=corr, lags=lags)

def hac_soma(g, lags: int = HAC_LAGS) -> float:
    """Variância de longo prazo de Newey-West (núcleo de Bartlett) de uma série de influência."""
    s = float(g @ g)
    for l in range(1, lags + 1): s += 2 * (1 - l / (lags + 1)) * float(g[l:] @ g[:-l])
    return s

def combinar(itens, pesos):
    """Combinação linear w1*beta1 + w2*beta2 + ... de log-RR de ajustes feitos nos MESMOS dias e com os MESMOS controles (por exemplo, o mesmo
    desfecho em dois locais de óbito). `itens` = lista de (ajuste, índice do contraste). O EP vem da série de influência combinada, então leva em conta
    a correlação entre as séries (mesmos dias, mesmo clima): é o equivalente ao teste de interação de um modelo empilhado com parâmetros de controle
    próprios de cada série. Devolve (estimativa, EP, RR, lo, hi, p)."""
    r0 = itens[0][0]
    for r, _ in itens: assert r["n"] == r0["n"] and r["p"] == r0["p"], "ajustes em dias diferentes"
    w = np.asarray(pesos, float)
    est = float(sum(wi * r["est"][j] for wi, (r, j) in zip(w, itens)))
    g = sum(wi * r["G"][j] for wi, (r, j) in zip(w, itens))
    se = float(np.sqrt(max(hac_soma(g, r0["lags"]) * r0["corr"], 0.0)))
    rr, lo, hi, p = ic(np.array([est]), np.array([se]))
    return est, se, float(rr[0]), float(lo[0]), float(hi[0]), float(p[0])

def wald_homog(itens):
    """Teste de Wald de igualdade dos log-RR de K ajustes nos mesmos dias (K-1 graus de liberdade), com a covariância HAC conjunta."""
    r0 = itens[0][0]; K = len(itens)
    G = np.vstack([r["G"][j] for r, j in itens])                        # K x ntot
    est = np.array([r["est"][j] for r, j in itens])
    L = r0["lags"]
    S = np.zeros((K, K))
    for l in range(0, L + 1):
        A = G[:, l:] @ G[:, :G.shape[1] - l].T
        S += A if l == 0 else (1 - l / (L + 1)) * (A + A.T)
    S *= r0["corr"]
    D = np.hstack([-np.ones((K - 1, 1)), np.eye(K - 1)])               # diferenças em relação ao primeiro
    dv = D @ est; V = D @ S @ D.T
    stat = float(dv @ np.linalg.solve(V, dv))
    from scipy.stats import chi2
    return stat, K - 1, float(chi2.sf(stat, K - 1))

def diferenca(ra, ja, rb, jb):
    """Pseudo-ajuste com um contraste = beta_a - beta_b (ajustes nos mesmos dias). Serve de entrada para `combinar` e `wald_homog`, por exemplo
    para testar se a diferença entre locais é a mesma em várias faixas etárias."""
    assert ra["n"] == rb["n"] and ra["p"] == rb["p"], "ajustes em dias diferentes"
    return dict(est=np.array([ra["est"][ja] - rb["est"][jb]]), G=np.array([ra["G"][ja] - rb["G"][jb]]), n=ra["n"], p=ra["p"], corr=ra["corr"], lags=ra["lags"])

def tendencia(itens, x):
    """Inclinação (por unidade de x) de uma regressão de mínimos quadrados generalizados dos contrastes `itens` (lista de (ajuste, índice)) sobre `x`,
    com a covariância HAC conjunta. Devolve (inclinação, EP, p)."""
    r0 = itens[0][0]; K = len(itens); L = r0["lags"]
    G = np.vstack([r["G"][j] for r, j in itens]); est = np.array([r["est"][j] for r, j in itens])
    S = np.zeros((K, K))
    for l in range(0, L + 1):
        Al = G[:, l:] @ G[:, :G.shape[1] - l].T
        S += Al if l == 0 else (1 - l / (L + 1)) * (Al + Al.T)
    S *= r0["corr"]
    Z = np.column_stack([np.ones(K), np.asarray(x, float)]); Si = np.linalg.inv(S)
    cov = np.linalg.inv(Z.T @ Si @ Z); b = cov @ Z.T @ Si @ est
    se = float(np.sqrt(cov[1, 1])); return float(b[1]), se, float(2 * norm.sf(abs(b[1] / se)))

def ic(est, se):
    return np.exp(est), np.exp(est - 1.96 * se), np.exp(est + 1.96 * se), 2 * norm.sf(np.abs(est / se))

def ajustar_dia(y_all, X_df: pd.DataFrame, an: Analise, periodo: str, df_ano: int | None = None, lags: int = HAC_LAGS, contrastes=None, mask=None):
    """Ajusta o modelo diário para um vetor de óbitos (todos os dias) e as colunas de exposição de `X_df`.
    `mask` (opcional) substitui a máscara do recorte (por exemplo, janela de atividade de uma unidade de saúde)."""
    if mask is None:
        m = an.mask[periodo]; C = an.controles(periodo, df_ano)
    else:
        m = np.asarray(mask, bool); C = an.controles_mascara(m, df_ano)
    X = np.column_stack([X_df.to_numpy(float)[m], C])
    return poisson_fit(np.asarray(y_all, float)[m], X, X_df.shape[1], tpos=an.t[m], ntot=len(an.t), lags=lags, contrastes=contrastes)

def bh(p):
    p = np.asarray(p, float); o = np.argsort(p); n = len(p); q = np.empty(n)
    q[o] = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    return np.minimum(q, 1)

# ---------------------------------------------------------------- semanas epidemiológicas
def semanas(dias):
    """Semanas epidemiológicas (domingo a sábado) completas dentro de `dias`. Devolve (início por dia, índices das semanas, tabela)."""
    ini = dias - pd.to_timedelta((dias.dayofweek + 1) % 7, unit="D")
    wed = ini + pd.Timedelta(days=3)
    ev = pd.DataFrame({"ini": ini, "ano": wed.year, "se": (wed.dayofyear - 1) // 7 + 1})
    nn = pd.Series(1, index=dias).groupby(ini).sum(); okw = nn[nn == 7].index
    wk = ev.drop_duplicates("ini").set_index("ini").loc[okw]
    return ini, okw, wk

def ajuste_semanal(yw, okw, mask_w, df_ano: int = DF_ANO):
    """Esperado semanal: Poisson com spline de tempo (df_ano gl por ano observado), ajustado só nas semanas não mascaradas.
    Nas semanas mascaradas (COVID, mês incompleto, sem clima) o esperado é NaN: sem dados ali, o spline não tem coeficientes determinados
    e a 'interpolação' pode ser arbitrária (principalmente em séries com poucos óbitos). Devolve (esperado, dispersão φ)."""
    t = np.arange(len(okw)); m = mask_w
    df = max(int(round(m.sum() / 52.18 * df_ano)), 4)
    dm = dmatrix(f"cr(x, df={df}) - 1", {"x": t[m]}, return_type="dataframe")
    B = np.asarray(dm); r = poisson_fit(np.asarray(yw, float)[m], B, 0, lags=0)
    Ball = base_prever(dm.design_info, np.clip(t, t[m].min(), t[m].max()))
    mu = np.exp(Ball @ r["b"]); phi = max(r["phi"], 1.0)
    mu[~m] = np.nan
    return mu, phi

def ajuste_diario(y_all, an: Analise, X=None, mask=None, df_ano: int | None = None):
    """Modelo diário da Figura 1: Poisson (log) com spline de tempo (df_ano gl por ano de dados) e dia da semana, ajustado nos dias de `mask`
    (padrão: recorte "Sem COVID"). `X` (opcional) é a exposição ao calor, 0/1 por dia, já com a janela de defasagem (dia de calor em t, t-1, t-2 ou t-3).
    O esperado é o contrafactual SEM calor: exp(spline + dia da semana), com a exposição zerada; sem `X`, é o modelo sem termo de calor.
    Fica NaN nos dias de COVID e de mês incompleto (sem dados ali o spline não é estimável). Devolve dict(mu, phi, rr, lo, hi); rr/lo/hi (EP robusto HAC) só com `X`."""
    df_ano = df_ano or an.df_ano; m = an.mask["Sem COVID"] if mask is None else np.asarray(mask, bool)
    C, di = controles_diarios(an.dias, m, df_ano); k = 0 if X is None else 1
    XX = C if X is None else np.column_stack([np.asarray(X, float)[m], C])
    r = poisson_fit(np.asarray(y_all, float)[m], XX, k, tpos=an.t[m], ntot=len(an.t), lags=HAC_LAGS if k else 0)
    t = an.t; B = base_prever(di, np.clip(t, t[m].min(), t[m].max()))
    dow = np.eye(7)[np.asarray(an.dias.dayofweek)][:, 1:]
    mu = np.exp(np.column_stack([B, dow]) @ r["b"][k:])
    mu[an.inc | an.covid] = np.nan
    out = dict(mu=mu, phi=max(float(r["phi"]), 1.0), rr=np.nan, lo=np.nan, hi=np.nan)
    if k: out["rr"], out["lo"], out["hi"], _ = (float(v[0]) for v in ic(r["est"], r["se"]))
    return out

# ---------------------------------------------------------------- contexto completo de uma análise
class Contexto:
    pass

def contexto(pop: str = "res", raiz: str = ".", inicio: str = INICIO, clima: str = "heat/data/temp_df.csv") -> Contexto:
    """Carrega óbitos, clima, período e máscaras. pop = 'res' (residentes que morreram no Rio) ou 'todos' (todos os óbitos ocorridos no Rio)."""
    raiz = Path(raiz)
    d_all = carregar_obitos(raiz / "silver_user/silver")
    cl = pd.read_csv(raiz / clima, parse_dates=["dia"]).sort_values("dia")
    an = pd.read_csv(raiz / "analise/anomalias_diarias.csv", parse_dates=["dia"])
    fim, ruins, mensal = definir_periodo(d_all, cl.loc[cl.hi_max.notna(), "dia"].max(), inicio)
    dias = pd.date_range(inicio, fim)
    d = d_all[(d_all.dia >= inicio) & (d_all.dia <= fim)]
    if pop == "res": d = d[d.residente]
    d = d.copy()
    nat = {c: eh_natural(c) for c in d.cid.unique()}; inf = {c: influenciado(c) for c in d.cid.unique()}; cov = {c: eh_covid(c) for c in d.cid.unique()}
    d["natural"] = d.cid.map(nat); d["sensivel"] = d.cid.map(inf); d["covid"] = d.cid.map(cov)
    d["local"] = classificar_local(d, tabela_cnes(raiz / "analise/cnes_estab.csv"))
    d["faixa"] = faixa_etaria(d.idade_anos)
    clima = Clima(dias, cl, an); A = Analise(dias, ruins, clima)
    cx = Contexto()
    cx.pop, cx.d, cx.d_all, cx.dias, cx.fim, cx.ruins, cx.mensal, cx.clima, cx.A = pop, d, d_all, dias, fim, ruins, mensal, clima, A
    return cx

def serie_dias(d: pd.DataFrame, dias) -> np.ndarray:
    return d.groupby("dia").size().reindex(dias, fill_value=0).to_numpy(float)

def series_local_faixa(d: pd.DataFrame, dias, locais=LOCAIS, faixas=FAIXAS) -> dict:
    """Contagens diárias por (local, faixa) mais os agregados 'Todos os locais' e 'Todas as idades'."""
    Y = {}
    for L in ["Todos os locais"] + list(locais):
        dl = d if L == "Todos os locais" else d[d.local == L]
        Y[(L, "Todas as idades")] = serie_dias(dl, dias)
        for fx in faixas: Y[(L, fx)] = serie_dias(dl[dl.faixa == fx], dias)
    return Y


def grade_semanal(cx):
    """Semanas epidemiológicas completas e máscara semanal (COVID e dados incompletos ficam fora do ajuste)."""
    ini, okw, wk = semanas(cx.dias)
    cov_w = pd.Series(cx.A.covid, index=cx.dias).groupby(ini).any().reindex(okw).to_numpy()
    inc_w = pd.Series(cx.A.inc | cx.clima.sem_clima, index=cx.dias).groupby(ini).any().reindex(okw).to_numpy()
    return ini, okw, wk, ~(cov_w | inc_w), cov_w, inc_w
