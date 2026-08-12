"""Collinearity diagnostic for exposome exposures + covariates (Paso 1).

Runs BEFORE any mortality regression. In Santiago the pollution-SES gradient
is geographic and steep; PM2.5, NO2, ALAN, noise and NSE are expected to be
near-collinear across the 52 communes. This script quantifies that so the
modeling steps commit to single-pollutant specifications instead of a
mutually-adjusted multi-exposure regression that collinearity cannot support.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402
from statsmodels.tools.tools import add_constant  # noqa: E402

MASTER_CSV = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.csv"
OUT_DIR = REPO_ROOT / "data" / "processed" / "analysis"

EXPOSURES = [
    "pm25_pop_weighted",
    "no2_surface_ug_m3",
    "heat_exposure_index",
    "sleep_context_index",
    "noise_combined_pct",
    "green_cover_pct_ndvi",
    "social_index",
    "walk_index",
    "transit_index",
    "food_index",
]
COVARIATES = ["nse_index", "demo_pct_pop_65_plus"]


def main() -> None:
    df = pd.read_csv(MASTER_CSV)
    cols = EXPOSURES + COVARIATES
    X = df[cols].dropna()
    n = len(X)

    # Pairwise Pearson + Spearman correlation matrices.
    pearson = X.corr(method="pearson")
    spearman = X.corr(method="spearman")

    # VIF: regress each variable on all others (with constant).
    Xc = add_constant(X)
    vif_rows = []
    for i, col in enumerate(cols):
        vif = variance_inflation_factor(Xc.values, i + 1)  # +1 to skip const
        vif_rows.append({"variable": col, "vif": round(float(vif), 3)})
    vif_df = pd.DataFrame(vif_rows).sort_values("vif", ascending=False)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pearson.to_csv(OUT_DIR / "exposure_collinearity_pearson.csv")
    spearman.to_csv(OUT_DIR / "exposure_collinearity_spearman.csv")
    vif_df.to_csv(OUT_DIR / "exposure_collinearity_vif.csv", index=False)

    print(f"n communes = {n}")
    print()
    print("VIF (>5 moderate concern, >10 severe -- single-pollutant models only above this line):")
    print(vif_df.to_string(index=False))
    print()
    print("High pairwise |Pearson r| > 0.6 among exposures/covariates:")
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r = pearson.loc[a, b]
            if abs(r) > 0.6:
                pairs.append((a, b, round(float(r), 3)))
    pairs.sort(key=lambda t: -abs(t[2]))
    for a, b, r in pairs:
        print(f"  {a:24s} <-> {b:24s}  r={r:+.3f}")
    if not pairs:
        print("  (none)")


if __name__ == "__main__":
    main()
