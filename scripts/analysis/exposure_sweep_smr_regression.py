"""Fase A2+A3: multi-exposure single-pollutant SMR sweep, standardized, FDR-corrected.

Extends the PM2.5-only ecological_smr_regression.py to every canonical exposome
axis. Each exposure is fit single-pollutant (one at a time) adjusted for SES and
age, because the VIF diagnostic (exposure_collinearity_vif.csv) shows the axes
are NOT mutually separable at n=52 -- NO2/walk/transit form a near-collinear
urban-form cluster and most axes trace one confounded pollution-SES gradient.

Design (per approved plan, honest framing baked in):
- Model: observed ~ z(exposure) + nse_index + demo_pct_pop_65_plus,
  offset=log(expected), Negative Binomial (Poisson is invalid here -- severe
  overdispersion, see prior doc).
- Each exposure is z-scored (mean 0, SD 1) so the rate ratio is reported per
  +1 SD and is comparable across axes of different units/signs. PM2.5's per-5ug
  RR is recoverable via the stored exposure_sd (continuity with the prior doc).
- Benjamini-Hochberg FDR is applied ONLY across the primary family
  (primary outcomes x exposures). Correcting across near-duplicate collinear
  exposures is not correcting across independent hypotheses -- q-values are
  reported but the collinearity structure (VIF/correlation) is the real
  interpretation, not the count of "significant" axes.
- Neuro outcomes are carried as exploratory (arm=exploratory_neuro), OUTSIDE the
  primary FDR family, so the sweep does not re-fish the already-quarantined
  latency-mismatched arm.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

ANALYSIS_DIR = REPO_ROOT / "data" / "processed" / "analysis"
SMR_CSV = ANALYSIS_DIR / "santiago_mortality_smr_by_cause.csv"
MASTER_CSV = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.csv"
PM25_HIST_CSV = REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2000_2017.csv"
OUT_CSV = ANALYSIS_DIR / "santiago_exposure_sweep_smr.csv"

# Canonical exposome axes (config/cities/santiago.yaml comparison.exposures) + ALAN + heavy metals.
EXPOSURES = [
    "pm25_pop_weighted",
    "pm25_hist",  # temporally-antecedent PM2.5 (2000-2017), merged below
    "no2_surface_ug_m3",
    "alan_radiance_pop_weighted",
    "noise_combined_pct",
    "heat_exposure_index",
    "green_cover_pct_ndvi",
    "walk_index",
    "transit_index",
    "social_index",
    "food_index",
    "sleep_context_index",
    "hm_index",
]
# Higher value = more of a plausibly-protective factor (RR<1 expected if it tracks lower mortality).
PROTECTIVE = {"green_cover_pct_ndvi", "walk_index", "transit_index", "social_index", "food_index"}

OUTCOMES_PRIMARY = ["all_cause", "cardiovascular", "respiratory",
                    "respiratory_pneumonia", "respiratory_acute_lower", "respiratory_copd"]
OUTCOMES_EXPLORATORY = ["dementia", "alzheimer", "cerebrovascular", "parkinsonism"]
COVARIATES = ["nse_index", "demo_pct_pop_65_plus"]


def fit_nb(df: pd.DataFrame, exposure: str) -> dict:
    z = (df[exposure] - df[exposure].mean()) / df[exposure].std(ddof=0)
    X = sm.add_constant(pd.concat([z.rename("z_exp"), df[COVARIATES]], axis=1))
    y = df["observed"].to_numpy()
    offset = np.log(df["expected"].to_numpy())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        poisson = sm.GLM(y, X, family=sm.families.Poisson(), offset=offset).fit()
        dispersion = float(poisson.pearson_chi2 / poisson.df_resid)
        nb = sm.NegativeBinomial(y, X, offset=offset).fit(disp=0, maxiter=300)

    coef = float(nb.params["z_exp"])
    se = float(nb.bse["z_exp"])
    return {
        "exposure": exposure,
        "n": int(len(df)),
        "exposure_mean": round(float(df[exposure].mean()), 4),
        "exposure_sd": round(float(df[exposure].std(ddof=0)), 4),
        "direction": "protective_if_neg" if exposure in PROTECTIVE else "harmful_if_pos",
        "poisson_dispersion": round(dispersion, 3),
        "rr_per_sd": round(float(np.exp(coef)), 4),
        "rr_lo": round(float(np.exp(coef - 1.96 * se)), 4),
        "rr_hi": round(float(np.exp(coef + 1.96 * se)), 4),
        "p": float(nb.pvalues["z_exp"]),
        "observed_total": int(df["observed"].sum()),
    }


def run(smr_csv: Path, out_csv: Path) -> None:
    smr = pd.read_csv(smr_csv)
    master = pd.read_csv(MASTER_CSV)[["name"] + COVARIATES + [e for e in EXPOSURES if e != "pm25_hist"]]
    hist = pd.read_csv(PM25_HIST_CSV)[["name", "pm25_pop_weighted"]].rename(
        columns={"pm25_pop_weighted": "pm25_hist"})
    covar = master.merge(hist, on="name", how="inner")

    rows = []
    for outcome in OUTCOMES_PRIMARY + OUTCOMES_EXPLORATORY:
        arm = "primary" if outcome in OUTCOMES_PRIMARY else "exploratory_neuro"
        sub = smr[smr["outcome"] == outcome].merge(covar, on="name", how="inner")
        if len(sub) != 52:
            print(f"WARN: {outcome} merged to {len(sub)} rows")
        for exposure in EXPOSURES:
            try:
                row = fit_nb(sub, exposure)
            except Exception as err:  # noqa: BLE001
                print(f"  NB failed {outcome}/{exposure}: {err}")
                continue
            row["outcome"] = outcome
            row["arm"] = arm
            rows.append(row)

    out = pd.DataFrame(rows)

    # A3: Benjamini-Hochberg FDR across the PRIMARY family only.
    out["q_bh_primary"] = np.nan
    prim = out["arm"] == "primary"
    out.loc[prim, "q_bh_primary"] = multipletests(out.loc[prim, "p"], method="fdr_bh")[1]

    cols = ["outcome", "arm", "exposure", "direction", "n", "observed_total",
            "exposure_mean", "exposure_sd", "poisson_dispersion",
            "rr_per_sd", "rr_lo", "rr_hi", "p", "q_bh_primary"]
    out = out[cols].sort_values(["arm", "outcome", "p"]).reset_index(drop=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 200)
    print(f"\nWrote {out_csv}\n")

    # Continuity check (mortality only): PM2.5 per-5ug RR recovered from the per-SD fit.
    pm_rows = out[(out["outcome"] == "cardiovascular") & (out["exposure"] == "pm25_hist")]
    if not pm_rows.empty:
        pm = pm_rows.iloc[0]
        rr_per_5ug = float(np.exp(np.log(pm["rr_per_sd"]) / pm["exposure_sd"] * 5.0))
        print(f"Continuity: cardiovascular ~ pm25_hist  RR/SD={pm['rr_per_sd']:.3f}  "
              f"=> RR/5ug={rr_per_5ug:.3f}  (mortality prior doc: 1.11)\n")

    print("PRIMARY family (sorted by q within outcome):")
    show = out[out["arm"] == "primary"].copy()
    show["p"] = show["p"].round(4)
    show["q_bh_primary"] = show["q_bh_primary"].round(4)
    print(show.to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smr-csv", type=Path, default=SMR_CSV,
                    help="SMR-by-cause CSV (name,outcome,observed,expected). Default: mortality.")
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV,
                    help="Output sweep CSV path.")
    args = ap.parse_args()
    run(args.smr_csv, args.out_csv)


if __name__ == "__main__":
    main()
