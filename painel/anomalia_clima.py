#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Índice de anomalia de temperatura: quão longe cada dia está da normal esperada.

Para cada estação e cada estatística diária (média, máxima, mínima) ajusta um GAM

    temperatura ~ s(tempo) + s(dia_do_ano, cíclico)

onde s(tempo) é a tendência de longo prazo (por padrão monotônica crescente, como pedido: a normal
só pode subir ou ficar estável) e s(dia_do_ano) é a sazonalidade anual, cíclica (31/12 emenda com 1/1).
Um segundo GAM, só no dia do ano, modela a variância (o verão varia menos que o inverno), então o
índice é comparável entre épocas do ano.

Saídas (em <raiz>/anomalia/)
----------------------------
temperatura_<estat>.parquet           por estação e dia: observado, esperado, desvio_padrao, anomalia,
                                      z, percentil_normal, percentil_emp, categoria
municipal_temperatura_<estat>.csv     média das anomalias e dos z das estações, por dia
ajustes.csv                           um resumo por estação/estatística: período, tendência (°C/década com
                                      IC), autocorrelação, qualidade do ajuste
comparacao_tendencia.csv              (opcional, --comparar) GCV/AIC de tendência livre, monotônica e linear

Observações
-----------
- Ajuste por estação: a média municipal bruta mistura estações que entram em anos diferentes e produz
  uma tendência falsa. Aqui a anomalia é calculada em cada estação e só então promediada.
- A temperatura diária é autocorrelacionada. Isso não enviesa o esperado, mas deixa os intervalos de
  confiança estreitos demais; o IC da tendência é inflado por sqrt((1+rho)/(1-rho)) (aproximação).
- A tendência de ~20 anos mistura aquecimento e variabilidade natural (El Niño etc.). Não é uma taxa
  de aquecimento do Rio; use como normal de referência móvel.

Uso
---
python anomalia_clima.py --raiz datalake/clima
python anomalia_clima.py --raiz datalake/clima --tendencia livre --comparar
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

log = logging.getLogger("anomalia")

ORIGEM_T = pd.Timestamp("2006-01-01")
ESTATS = {"media": "media", "max": "max", "min": "min"}
CORRECAO_LOG_CHI2 = 1.2704  # -E[log(chi2_1)]: corrige o viés de ajustar log(resíduo^2)

CATEGORIAS = [(-np.inf, -2, "muito abaixo"), (-2, -1, "abaixo"), (-1, 1, "normal"),
              (1, 2, "acima"), (2, np.inf, "muito acima")]


def _gam_classes():
    from pygam import LinearGAM, l, s
    return LinearGAM, l, s


def carregar_diario(raiz: Path, variavel: str = "temperatura") -> pd.DataFrame:
    base = raiz / "diario" / variavel
    arqs = sorted(base.glob("ano=*/part-0.parquet"))
    if not arqs:
        raise FileNotFoundError(f"Sem dados em {base}")
    d = pd.concat([pd.read_parquet(a) for a in arqs], ignore_index=True)
    d["dia"] = pd.to_datetime(d["dia"])
    return d.drop_duplicates(["fonte", "estacao_id", "dia"]).sort_values(["fonte", "estacao_id", "dia"])


def _features(dia: pd.Series) -> np.ndarray:
    t = (dia - ORIGEM_T).dt.days.to_numpy(float) / 365.25
    doy = dia.dt.dayofyear.to_numpy(float) - 0.5     # 0,5 .. 365,5 (366,5 em bissexto)
    return np.column_stack([t, doy])


def _termos(modo: str, k_tendencia: int, k_doy: int):
    LinearGAM, l, s = _gam_classes()
    if modo == "monotonica":
        tend = s(0, n_splines=k_tendencia, basis="ps", constraints="monotonic_inc")
    elif modo == "livre":
        tend = s(0, n_splines=k_tendencia, basis="ps")
    elif modo == "linear":
        tend = l(0)
    else:
        raise ValueError(modo)
    return tend + s(1, n_splines=k_doy, basis="cp", edge_knots=[0.0, 366.0])


def _ajustar_media(X: np.ndarray, y: np.ndarray, modo: str, k_tendencia: int, k_doy: int):
    LinearGAM, _, _ = _gam_classes()
    gam = LinearGAM(_termos(modo, k_tendencia, k_doy))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gam.gridsearch(X, y, lam=np.logspace(-1, 3, 5), progress=False)
    return gam


def _ajustar_variancia(doy: np.ndarray, resid: np.ndarray, k: int = 6):
    LinearGAM, _, s = _gam_classes()
    alvo = np.log(np.maximum(resid ** 2, 1e-4))
    gam = LinearGAM(s(0, n_splines=k, basis="cp", edge_knots=[0.0, 366.0]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gam.gridsearch(doy.reshape(-1, 1), alvo, lam=np.logspace(0, 4, 5), progress=False)
    return gam


def _categoria(z: np.ndarray) -> np.ndarray:
    out = np.full(z.shape, "normal", dtype=object)
    for lo, hi, nome in CATEGORIAS:
        out[(z >= lo) & (z < hi)] = nome
    out[np.isnan(z)] = None
    return out


def _lag1(x: np.ndarray, dias: np.ndarray) -> float:
    """Autocorrelação lag-1 usando só pares de dias consecutivos."""
    ok = (np.diff(dias) == 1) & ~np.isnan(x[1:]) & ~np.isnan(x[:-1])
    if ok.sum() < 30:
        return float("nan")
    a, b = x[:-1][ok], x[1:][ok]
    return float(np.corrcoef(a, b)[0, 1])


def ajustar_serie(dias: pd.Series, y: np.ndarray, modo: str, k_tendencia: int, k_doy: int):
    """Devolve DataFrame (esperado, desvio, z, ...) e dicionário-resumo."""
    X = _features(dias)
    gam = _ajustar_media(X, y, modo, k_tendencia, k_doy)
    esperado = gam.predict(X)
    resid = y - esperado
    gv = _ajustar_variancia(X[:, 1], resid)
    var = np.exp(gv.predict(X[:, 1].reshape(-1, 1)) + CORRECAO_LOG_CHI2)
    dp = np.sqrt(var)
    z = resid / dp

    dia_num = (dias - dias.min()).dt.days.to_numpy()
    rho = _lag1(resid, dia_num)
    infl = np.sqrt((1 + rho) / (1 - rho)) if np.isfinite(rho) and rho < 0.99 else np.nan

    # tendência: variação da componente s(tempo) entre o início e o fim do período
    t0, t1 = X[:, 0].min(), X[:, 0].max()
    doy_ref = 183.0
    XX = np.array([[t0, doy_ref], [t1, doy_ref]])
    pd_ = gam.partial_dependence(term=0, X=XX, width=0.95)
    f, ci = pd_
    delta = float(f[1] - f[0])
    se = [((ci[i][1] - ci[i][0]) / 2) / 1.96 for i in (0, 1)]
    se_delta = float(np.hypot(se[0], se[1])) * (infl if np.isfinite(infl) else 1.0)
    anos = t1 - t0
    resumo = dict(
        modo_tendencia=modo, n_dias=int(len(y)),
        primeiro_dia=dias.min().date(), ultimo_dia=dias.max().date(), anos_cobertos=round(float(anos), 2),
        tendencia_total_c=round(delta, 3),
        tendencia_c_por_decada=round(delta / anos * 10, 3) if anos > 0 else np.nan,
        ic95_inf_c_por_decada=round((delta - 1.96 * se_delta) / anos * 10, 3) if anos > 0 else np.nan,
        ic95_sup_c_por_decada=round((delta + 1.96 * se_delta) / anos * 10, 3) if anos > 0 else np.nan,
        rho_lag1=round(rho, 3) if np.isfinite(rho) else np.nan,
        pseudo_r2=round(float(gam.statistics_["pseudo_r2"]["McFadden_adj"]), 3),
        gcv=round(float(gam.statistics_["GCV"]), 4), aic=round(float(gam.statistics_["AIC"]), 1),
        edf=round(float(gam.statistics_["edof"]), 1),
        dp_medio_c=round(float(np.mean(dp)), 3),
        dp_residual_c=round(float(np.std(resid)), 3),
    )
    z_ord = stats.rankdata(z, nan_policy="omit")
    out = pd.DataFrame({
        "observado": y, "esperado": esperado, "desvio_padrao": dp,
        "anomalia": resid, "z": z,
        "percentil_normal": stats.norm.cdf(z) * 100,
        "percentil_emp": z_ord / (np.sum(~np.isnan(z)) + 1) * 100,
        "categoria": _categoria(z),
    })
    return out, resumo


def processar(raiz: Path, saida: Path, variavel: str, estats: list[str], modo: str,
              k_tendencia: int, k_doy: int, min_anos: float, comparar: bool) -> int:
    d = carregar_diario(raiz, variavel)
    saida.mkdir(parents=True, exist_ok=True)
    ajustes, comparacao = [], []
    for est in estats:
        col = ESTATS[est]
        if col not in d.columns:
            log.warning("Estatística %s ausente em %s", col, variavel)
            continue
        partes = []
        for (fonte, eid), g in d.groupby(["fonte", "estacao_id"]):
            g = g[g[col].notna()]
            if len(g) < 365 * 2:
                log.info("%s %s %s: só %d dias, ignorada", fonte, eid, est, len(g))
                continue
            anos = (g["dia"].max() - g["dia"].min()).days / 365.25
            if anos < min_anos:
                log.info("%s %s %s: período de %.1f anos < %.0f, ignorada", fonte, eid, est, anos, min_anos)
                continue
            y = g[col].to_numpy(float)
            try:
                out, res = ajustar_serie(g["dia"], y, modo, k_tendencia, k_doy)
            except Exception as e:  # noqa: BLE001
                log.error("%s %s %s: ajuste falhou: %s", fonte, eid, est, e)
                continue
            out.insert(0, "dia", g["dia"].to_numpy())
            out.insert(0, "estacao_id", eid)
            out.insert(0, "fonte", fonte)
            partes.append(out)
            ajustes.append(dict(fonte=fonte, estacao_id=eid, estatistica=est, **res))
            log.info("%s %s %s: %d dias, tendência %.2f °C/década, rho=%.2f", fonte, eid, est, len(g),
                     res["tendencia_c_por_decada"], res["rho_lag1"])
            if comparar:
                for m in ("livre", "monotonica", "linear"):
                    try:
                        _, r2 = ajustar_serie(g["dia"], y, m, k_tendencia, k_doy)
                        comparacao.append(dict(fonte=fonte, estacao_id=eid, estatistica=est, modo=m,
                                               gcv=r2["gcv"], aic=r2["aic"], edf=r2["edf"],
                                               tendencia_c_por_decada=r2["tendencia_c_por_decada"]))
                    except Exception as e:  # noqa: BLE001
                        log.warning("comparação %s falhou: %s", m, e)
        if not partes:
            continue
        todo = pd.concat(partes, ignore_index=True)
        todo.to_parquet(saida / f"temperatura_{est}.parquet", index=False)
        mun = (todo.groupby("dia")
               .agg(anomalia_media=("anomalia", "mean"), z_medio=("z", "mean"),
                    esperado_medio=("esperado", "mean"), observado_medio=("observado", "mean"),
                    n_estacoes=("estacao_id", "nunique"))
               .reset_index())
        mun["categoria"] = _categoria(mun["z_medio"].to_numpy())
        cols_num = mun.select_dtypes("number").columns
        mun[cols_num] = mun[cols_num].round(3)
        mun.to_csv(saida / f"municipal_temperatura_{est}.csv", index=False)
        log.info("temperatura_%s: %s linhas, %d estações", est, f"{len(todo):,}", todo["estacao_id"].nunique())
    if ajustes:
        pd.DataFrame(ajustes).to_csv(saida / "ajustes.csv", index=False)
    if comparacao:
        pd.DataFrame(comparacao).to_csv(saida / "comparacao_tendencia.csv", index=False)
    return 0 if ajustes else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, default=Path("datalake/clima"))
    ap.add_argument("--saida", type=Path, default=None, help="padrão: <raiz>/anomalia")
    ap.add_argument("--variavel", default="temperatura")
    ap.add_argument("--estatisticas", nargs="*", choices=list(ESTATS), default=["media", "max", "min"])
    ap.add_argument("--tendencia", choices=["monotonica", "livre", "linear"], default="monotonica")
    ap.add_argument("--k-tendencia", type=int, default=12, help="nº de splines da tendência")
    ap.add_argument("--k-doy", type=int, default=8, help="nº de splines do dia do ano")
    ap.add_argument("--min-anos", type=float, default=8.0, help="período mínimo por estação (anos)")
    ap.add_argument("--comparar", action="store_true", help="grava GCV/AIC das três formas de tendência")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    sys.exit(processar(a.raiz, a.saida or a.raiz / "anomalia", a.variavel, a.estatisticas, a.tendencia,
                       a.k_tendencia, a.k_doy, a.min_anos, a.comparar))


if __name__ == "__main__":
    main()
