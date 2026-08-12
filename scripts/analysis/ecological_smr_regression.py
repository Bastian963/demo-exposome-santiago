"""Paso 4: ecological SMR regression, single-pollutant, SES-adjusted.

Poisson / negative-binomial GLM on observed deaths with offset=log(expected)
(indirect age standardization from build_smr_by_cause.py). Single-pollutant
models only (see data/processed/analysis/exposure_collinearity_vif.csv:
NO2/walk/transit form a near-collinear urban-form cluster; PM2.5 is
comparatively independent, VIF ~3.2).

Primary exposure: historical antecedent PM2.5 (2000-2017, precedes the
2018-2022 mortality window). Sensitivity: contemporary PM2.5 (2015-2022,
overlaps the mortality window) for comparison.

Model: log(E[observed]) = log(expected) + b0 + b1*pm25 + b2*nse_index +
b3*demo_pct_pop_65_plus. Rate ratio reported per 5 ug/m3 PM2.5 increase.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

SMR_CSV = REPO_ROOT / "data" / "processed" / "analysis" / "santiago_mortality_smr_by_cause.csv"
MASTER_CSV = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.csv"
PM25_HIST_CSV = REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2000_2017.csv"
OUT_CSV = REPO_ROOT / "data" / "processed" / "analysis" / "santiago_mortality_smr_regression.csv"

OUTCOMES_PRIMARY = ["all_cause", "cardiovascular", "respiratory"]
OUTCOMES_EXPLORATORY = ["dementia", "alzheimer", "cerebrovascular", "parkinsonism"]
COVARIATES = ["nse_index", "demo_pct_pop_65_plus"]
PM25_STEP = 5.0  # report rate ratio per 5 ug/m3 increase


def fit_one(df: pd.DataFrame, pm25_col: str, covariates: list[str]) -> dict:
    y = df["observed"].to_numpy()
    offset = np.log(df["expected"].to_numpy())
    X = sm.add_constant(df[[pm25_col] + covariates])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        poisson_res = sm.GLM(y, X, family=sm.families.Poisson(), offset=offset).fit()

    # Overdispersion check: Pearson chi2 / df. >1.5 suggests NB is more appropriate.
    dispersion = poisson_res.pearson_chi2 / poisson_res.df_resid

    nb_res = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            nb_res = sm.NegativeBinomial(y, X, offset=offset).fit(disp=0, maxiter=200)
    except Exception as err:  # noqa: BLE001
        print(f"  NB fit failed for {pm25_col}: {err}")

    row = {
        "exposure": pm25_col,
        "n": len(df),
        "poisson_dispersion": round(float(dispersion), 3),
        "poisson_coef": poisson_res.params[pm25_col],
        "poisson_se": poisson_res.bse[pm25_col],
        "poisson_p": poisson_res.pvalues[pm25_col],
    }
    row["poisson_rr_per_5ug"] = float(np.exp(row["poisson_coef"] * PM25_STEP))
    row["poisson_rr_lo"] = float(np.exp((row["poisson_coef"] - 1.96 * row["poisson_se"]) * PM25_STEP))
    row["poisson_rr_hi"] = float(np.exp((row["poisson_coef"] + 1.96 * row["poisson_se"]) * PM25_STEP))

    if nb_res is not None:
        row["nb_coef"] = nb_res.params[pm25_col]
        row["nb_se"] = nb_res.bse[pm25_col]
        row["nb_p"] = nb_res.pvalues[pm25_col]
        row["nb_rr_per_5ug"] = float(np.exp(row["nb_coef"] * PM25_STEP))
        row["nb_rr_lo"] = float(np.exp((row["nb_coef"] - 1.96 * row["nb_se"]) * PM25_STEP))
        row["nb_rr_hi"] = float(np.exp((row["nb_coef"] + 1.96 * row["nb_se"]) * PM25_STEP))
    return row


def main() -> None:
    smr = pd.read_csv(SMR_CSV)
    master = pd.read_csv(MASTER_CSV)[["name"] + COVARIATES + ["pm25_pop_weighted"]].rename(
        columns={"pm25_pop_weighted": "pm25_recent"}
    )
    hist = pd.read_csv(PM25_HIST_CSV)[["name", "pm25_pop_weighted"]].rename(
        columns={"pm25_pop_weighted": "pm25_hist"}
    )
    covar = master.merge(hist, on="name", how="inner")

    results = []
    for outcome in OUTCOMES_PRIMARY + OUTCOMES_EXPLORATORY:
        sub = smr[smr["outcome"] == outcome].merge(covar, on="name", how="inner")
        if len(sub) != 52:
            print(f"WARN: {outcome} merged to {len(sub)} rows, expected 52")

        for pm25_col in ["pm25_hist", "pm25_recent"]:
            row = fit_one(sub, pm25_col, COVARIATES)
            row["outcome"] = outcome
            row["arm"] = "primary" if outcome in OUTCOMES_PRIMARY else "exploratory_neuro"
            results.append(row)

    out = pd.DataFrame(results)
    cols = ["outcome", "arm", "exposure", "n", "poisson_dispersion",
            "poisson_rr_per_5ug", "poisson_rr_lo", "poisson_rr_hi", "poisson_p",
            "nb_rr_per_5ug", "nb_rr_lo", "nb_rr_hi", "nb_p"]
    out = out[cols]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    print(f"\nWrote {OUT_CSV}\n")
    print(out.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
