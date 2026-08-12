"""Paso 5-6: spatial-autocorrelation diagnostic + negative-control robustness check.

1. Moran's I on NB regression residuals (queen contiguity over the 52 communes).
   High residual spatial autocorrelation would mean a non-spatial model leaves
   structure unexplained -> motivates a BYM hardening pass. Low/non-significant
   autocorrelation means the SES-adjusted non-spatial NB model is already
   reasonably well-specified, and a spatial term is a sensitivity check rather
   than a necessity (per the plan: spatial confounding cuts both ways -- a BYM
   term can absorb a spatially-smooth exposure's true effect just as easily as
   it can absorb nuisance structure, so it is reported as a comparison, not
   treated as automatically superior).

2. Negative control: injury/poisoning mortality (ICD-10 chapter XIX, S00-T98 --
   the "nature of injury" codes DEIS actually records in DIAG1 for accidents,
   assault, self-harm and transport injury; there are zero V01-Y89 "external
   cause" codes in this DIAG1 field, confirmed empirically) has no known
   biologically plausible link to chronic PM2.5 exposure. If PM2.5 "predicts"
   these deaths
   too, that is a red flag for uncontrolled area-level confounding (e.g. PM2.5
   proxying for something structural like poverty/urban form that drives many
   causes of death, not a specific PM2.5 pathway). If PM2.5 does NOT predict
   external causes, that supports the cardiovascular/all-cause associations
   being more than a generic confounding artifact.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.neuro_mortality import _clean_icd_code, _icd_matches  # noqa: E402
from exposome import demography  # noqa: E402

DEIS_CSV = REPO_ROOT / "data" / "raw" / "deis" / "defunciones" / "DEFUNCIONES_FUENTE_DEIS_1990_2023_CIFRAS_OFICIALES.csv"
MASTER_GEOJSON = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.geojson"
MASTER_CSV = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.csv"
PM25_HIST_CSV = REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2000_2017.csv"
REG_CSV = REPO_ROOT / "data" / "processed" / "analysis" / "santiago_mortality_smr_regression.csv"
CACHE_DIR = REPO_ROOT / "cache"
OUT_DIR = REPO_ROOT / "data" / "processed" / "analysis"

YEARS = {2018, 2019, 2020, 2021, 2022}
AGE_BINS = ("0_14", "15_64", "65_plus")
N_YEARS = 5
COVARIATES = ["nse_index", "demo_pct_pop_65_plus"]

# Injury/poisoning (ICD-10 chapter XIX): transport accidents, falls, assault,
# self-harm, other injury -- the codes DEIS actually populates in DIAG1 for
# these deaths (confirmed empirically: zero V01-Y89 codes appear in DIAG1).
EXTERNAL_CAUSE_PREFIXES = tuple(f"S{i:02d}" for i in range(0, 100)) + \
    tuple(f"T{i:02d}" for i in range(0, 99))


def moran_i_check(residuals: pd.Series, names: pd.Index) -> dict:
    import libpysal
    from esda.moran import Moran

    gdf = gpd.read_file(MASTER_GEOJSON)[["name", "geometry"]].set_index("name").loc[names]
    w = libpysal.weights.Queen.from_dataframe(gdf, use_index=True)
    w.transform = "r"
    mi = Moran(residuals.loc[gdf.index].to_numpy(), w)
    return {"morans_i": round(float(mi.I), 4), "p_sim": round(float(mi.p_sim), 4), "z_sim": round(float(mi.z_sim), 4)}


def build_external_cause_smr() -> pd.DataFrame:
    raw = pd.read_csv(DEIS_CSV, sep=";", encoding="latin1", low_memory=False)
    raw["year"] = pd.to_numeric(raw["AÑO"], errors="coerce")
    raw = raw[raw["year"].isin(YEARS)].copy()
    raw = raw[raw["NOMBRE_REGION"].astype(str).str.contains("Metropolitana", case=False, na=False)].copy()

    code_map = demography.load_comuna_code_name_map(CACHE_DIR, region_code=13)
    raw["comuna_code"] = pd.to_numeric(raw["COD_COMUNA"], errors="coerce").astype("Int64")
    raw = raw.merge(code_map[["comuna_code", "name"]], on="comuna_code", how="left")
    raw = raw[raw["name"].notna()].copy()
    raw["name"] = demography.normalize_comuna_name(raw["name"])
    raw = raw[raw["name"].isin(set(code_map["name"]))].copy()

    raw["cause_code"] = raw["DIAG1"].map(_clean_icd_code)
    is_external = raw["cause_code"].map(lambda c: _icd_matches(c, EXTERNAL_CAUSE_PREFIXES))
    sub = raw[is_external].copy()

    age_num = pd.to_numeric(sub["EDAD_CANT"], errors="coerce")
    age_type = sub["EDAD_TYPE"] if "EDAD_TYPE" in sub.columns else sub.get("EDAD_TIPO")
    bins = []
    for age_val, type_val in zip(age_num, sub["EDAD_TIPO"]):
        t = str(type_val).strip()
        if t in {"2", "2.0", "3", "3.0", "4", "4.0"}:
            bins.append("0_14")
        elif pd.notna(age_val):
            a = float(age_val)
            bins.append("0_14" if a <= 14 else "15_64" if a <= 64 else "65_plus")
        else:
            bins.append(None)
    sub["age_bin"] = bins

    demo = demography.load_commune_demography(CACHE_DIR, region_code=13).set_index("name")
    demo = demo[["pop_0_14", "pop_15_64", "pop_65_plus", "pop_total"]]

    counts = sub.groupby(["name", "age_bin"]).size().unstack("age_bin", fill_value=0).reindex(columns=list(AGE_BINS), fill_value=0)
    observed_total = counts.sum(axis=1)

    ref_rates = {ab: counts[ab].sum() / (demo.loc[counts.index, f"pop_{ab}"].sum() * N_YEARS) for ab in AGE_BINS}

    rows = []
    for name in demo.index:
        obs = float(observed_total.get(name, 0.0))
        exp = sum(ref_rates[ab] * demo.loc[name, f"pop_{ab}"] * N_YEARS for ab in AGE_BINS)
        rows.append({"name": name, "outcome": "external_causes_negctrl", "observed": obs,
                      "expected": round(exp, 4), "smr": round(obs / exp, 4) if exp > 0 else np.nan})
    return pd.DataFrame(rows)


def fit_nb(df: pd.DataFrame, pm25_col: str) -> tuple[dict, pd.Series]:
    y = df["observed"].to_numpy()
    offset = np.log(df["expected"].to_numpy())
    X = sm.add_constant(df[[pm25_col] + COVARIATES])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = sm.NegativeBinomial(y, X, offset=offset).fit(disp=0, maxiter=200)
    rr = float(np.exp(res.params[pm25_col] * 5.0))
    lo = float(np.exp((res.params[pm25_col] - 1.96 * res.bse[pm25_col]) * 5.0))
    hi = float(np.exp((res.params[pm25_col] + 1.96 * res.bse[pm25_col]) * 5.0))
    row = {"exposure": pm25_col, "n": len(df), "nb_rr_per_5ug": rr, "nb_rr_lo": lo, "nb_rr_hi": hi,
           "nb_p": float(res.pvalues[pm25_col])}
    resid = pd.Series(res.resid_pearson, index=df["name"]) if hasattr(res, "resid_pearson") else pd.Series(res.resid, index=df["name"])
    return row, resid


def main() -> None:
    master = pd.read_csv(MASTER_CSV)[["name"] + COVARIATES]
    hist = pd.read_csv(PM25_HIST_CSV)[["name", "pm25_pop_weighted"]].rename(columns={"pm25_pop_weighted": "pm25_hist"})
    covar = master.merge(hist, on="name", how="inner")

    # --- 1. Moran's I on NB residuals for the primary causes ---
    print("=" * 70)
    print("SPATIAL AUTOCORRELATION CHECK (Moran's I on NB residuals, queen contiguity)")
    print("=" * 70)
    smr = pd.read_csv(REPO_ROOT / "data" / "processed" / "analysis" / "santiago_mortality_smr_by_cause.csv")
    moran_rows = []
    for outcome in ["all_cause", "cardiovascular", "respiratory"]:
        sub = smr[smr["outcome"] == outcome].merge(covar, on="name", how="inner")
        _, resid = fit_nb(sub, "pm25_hist")
        mi = moran_i_check(resid, sub.set_index("name").index)
        mi["outcome"] = outcome
        moran_rows.append(mi)
        sig = "SIGNIFICANT (p<0.05)" if mi["p_sim"] < 0.05 else "not significant"
        print(f"  {outcome:16s}  Moran's I={mi['morans_i']:+.4f}  z={mi['z_sim']:+.3f}  p={mi['p_sim']:.4f}  -> {sig}")
    pd.DataFrame(moran_rows).to_csv(OUT_DIR / "residual_morans_i.csv", index=False)

    # --- 2. Negative control: external-cause mortality ---
    print()
    print("=" * 70)
    print("NEGATIVE CONTROL: injury/poisoning mortality (S00-T98) vs PM2.5")
    print("=" * 70)
    negctrl = build_external_cause_smr()
    sub = negctrl.merge(covar, on="name", how="inner")
    neg_rows = []
    for pm25_col in ["pm25_hist"]:
        row, _ = fit_nb(sub, pm25_col)
        row["outcome"] = "external_causes_negctrl"
        neg_rows.append(row)
    neg_df = pd.DataFrame(neg_rows)
    neg_df.to_csv(OUT_DIR / "negative_control_external_causes.csv", index=False)
    print(neg_df.round(4).to_string(index=False))
    flag = "RED FLAG: PM2.5 spuriously predicts external causes" if neg_df["nb_p"].iloc[0] < 0.05 else \
           "PASS: no spurious association with external causes"
    print(f"\n  -> {flag}")


if __name__ == "__main__":
    main()
