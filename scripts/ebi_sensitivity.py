"""EBI sensitivity analysis: leave-one-layer-out (jackknife).

Re-computes the Environmental Burden Index (EBI) **without**
each canonical indicator (one at a time) and reports how much
the per-commune EBI score changes. The most influential
indicator is the one whose removal changes the EBI the most.

The script produces:

1. **Per-indicator influence** (Spearman of full EBI vs EBI
   without indicator k, and the change in top-5 communes).
2. **Tornado plot** of mean absolute EBI change per indicator.
3. **Top-5 stability**: how often each commune appears in the
   top 5 across all 21 jackknife variants.
4. **JSON summary** with the influence ranking.

Outputs
-------
- ``data/processed/ebi_sensitivity.json``
- ``figures/ebi_sensitivity_tornado.png``
- ``data/processed/ebi_sensitivity.csv`` (long-format: 21 rows
  per indicator x 52 communes = 1092 rows)

Usage
-----
    python scripts/ebi_sensitivity.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
FIGURES_DIR = REPO_ROOT / "figures"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
    }
)


# Same canonical set as scripts/analyze_cross_layer.py.
CANONICAL_INDICATORS: list[tuple[str, str, int]] = [
    ("PM2.5 (ACAG)", "pm25_mean", +1),
    ("NO2 surface (sat)", "no2_surface_ug_m3", +1),
    ("O3 column (sat)", "o3_mean", +1),
    ("AOD 470 nm", "aod_470", +1),
    ("Heavy metals index", "hm_index", +1),
    ("ALAN radiance", "alan_radiance_mean", +1),
    ("Noise (combined %)", "noise_combined_pct", +1),
    ("Heat exposure", "heat_exposure_index", +1),
    ("Urban heat anomaly (C)", "urban_heat_anomaly_c", +1),
    ("Wildfire burned pct", "fire_burned_pct_mean_annual", +1),
    ("Wind calm annual", "wind_calm_pct", +1),
    ("Greenspace coverage NDVI", "green_cover_pct_ndvi", -1),
    ("Green area km2", "green_km2", -1),
    ("Walkability index", "walk_index", -1),
    ("Transit index", "transit_index", -1),
    ("Primary care density", "health_n_primary_care", -1),
    ("Food swamp ratio", "food_swamp_ratio", +1),
    ("Pobreza %", "pobreza_pct", +1),
    ("NSE index", "nse_index", -1),
    ("Hacinamiento", "hacinamiento_phh", +1),
]


def _load_master_and_ebi() -> tuple[pd.DataFrame, pd.DataFrame]:
    master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
    ebi = pd.read_csv(DATA_DIR / "environmental_burden_index.csv")
    return master, ebi


def _rank_percentile(s: pd.Series, direction: int) -> pd.Series:
    """Convert to [0, 1] rank-percentile, sign-adjusted by direction."""
    r = s.rank(pct=True, na_option="bottom")
    if direction == -1:
        r = 1.0 - r
    return r.fillna(0.5)


def _compute_ebi_for(
    df: pd.DataFrame,
    indicators: list[tuple[str, str, int]],
) -> pd.Series:
    """Re-compute EBI from scratch using only the given indicator list."""
    pct = pd.DataFrame(index=df.index)
    for label, col, direction in indicators:
        if col in df.columns and df[col].notna().sum() >= 30:
            pct[f"pct_{col}"] = _rank_percentile(df[col], direction)
    return pct.mean(axis=1)


def _spearman_with_pvalues(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    valid = x.notna() & y.notna()
    if valid.sum() < 10:
        return float("nan"), float("nan")
    rho, p = spearmanr(x[valid], y[valid])
    return float(rho), float(p)


def main() -> None:
    print("Loading master + EBI...")
    master, ebi_full = _load_master_and_ebi()
    ebi_full_score = ebi_full.set_index("name")["ebi_score"]
    master = master.set_index("name")

    print("Running leave-one-out jackknife (21 variants)...")
    rows: list[dict] = []
    influence: list[dict] = []
    top5_counts: dict[str, int] = {n: 0 for n in master.index}

    for excluded_idx, (excl_label, excl_col, _) in enumerate(CANONICAL_INDICATORS):
        reduced = [
            (l, c, d) for (l, c, d) in CANONICAL_INDICATORS
            if not (l == excl_label and c == excl_col)
        ]
        ebi_loo = _compute_ebi_for(master, reduced)
        ebi_loo.name = "ebi_loo"
        ebi_loo.index = master.index

        rho, p = _spearman_with_pvalues(
            ebi_full_score.reindex(ebi_loo.index),
            ebi_loo,
        )
        mean_abs_diff = float(
            (ebi_full_score.reindex(ebi_loo.index) - ebi_loo).abs().mean(),
        )
        top5 = (
            ebi_loo
            .sort_values(ascending=False)
            .head(5)
            .index
            .tolist()
        )
        for n in top5:
            if n in top5_counts:
                top5_counts[n] += 1
        n_communes_changed = int(
            (ebi_loo.rank(ascending=False) !=
             ebi_full_score.reindex(ebi_loo.index).rank(ascending=False)
            ).sum()
        )

        influence.append(
            {
                "excluded_label": excl_label,
                "excluded_col": excl_col,
                "spearman_rho_vs_full": round(rho, 4),
                "spearman_p": round(p, 4),
                "mean_abs_ebi_diff": round(mean_abs_diff, 4),
                "n_top5_communes": len(top5),
                "top5_communes": top5,
                "n_communes_rank_changed": n_communes_changed,
            }
        )
        for name, ebi_val in ebi_loo.items():
            full_val = float(ebi_full_score.loc[name])
            rows.append(
                {
                    "excluded_label": excl_label,
                    "excluded_col": excl_col,
                    "name": name,
                    "ebi_full": round(full_val, 4),
                    "ebi_loo": round(float(ebi_val), 4),
                    "delta": round(float(ebi_val) - full_val, 4),
                }
            )

        print(
            f"  Excl. {excl_label:30s}  "
            f"rho={rho:+.4f}  mean|delta|={mean_abs_diff:.4f}  "
            f"top5={top5[0]}"
        )

    influence_df = (
        pd.DataFrame(influence)
        .sort_values("mean_abs_ebi_diff", ascending=False)
        .reset_index(drop=True)
    )
    print("\nMost influential indicator: "
          f"{influence_df.iloc[0]['excluded_label']} "
          f"(mean |delta| = {influence_df.iloc[0]['mean_abs_ebi_diff']:.4f})")

    print("\nTop-5 commune stability across 21 jackknife variants:")
    for name, count in sorted(
        top5_counts.items(), key=lambda kv: -kv[1]
    )[:10]:
        if count > 0:
            print(f"  {name:30s} in top-5 in {count}/21 variants")

    loo_csv = DATA_DIR / "ebi_sensitivity.csv"
    pd.DataFrame(rows).to_csv(loo_csv, index=False)
    print(f"\nWrote: {loo_csv} ({len(rows)} rows)")

    fig, ax = plt.subplots(figsize=(9, 7))
    plot_df = influence_df.sort_values("mean_abs_ebi_diff", ascending=True)
    ax.barh(
        plot_df["excluded_label"],
        plot_df["mean_abs_ebi_diff"],
        color="#d7191c",
        edgecolor="white",
    )
    for i, (v, rho) in enumerate(zip(
        plot_df["mean_abs_ebi_diff"], plot_df["spearman_rho_vs_full"],
    )):
        ax.text(
            v + 0.001, i, f"rho={rho:+.3f}",
            va="center", fontsize=7, color="black",
        )
    ax.set_xlabel("Mean |EBI_loo - EBI_full|", fontsize=9)
    ax.set_title(
        "EBI sensitivity (leave-one-layer-out jackknife)\n"
        "Higher = more influential; rho = correlation of EBI_loo vs EBI_full",
        fontsize=10.5,
    )
    plt.tight_layout()
    out_fig = FIGURES_DIR / "ebi_sensitivity_tornado.png"
    plt.savefig(out_fig, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_fig}")

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Leave-one-layer-out jackknife: EBI is re-computed from "
            "scratch 21 times (full + 20 indicators removed one at a "
            "time). For each variant we report Spearman rho vs the "
            "full EBI, the mean absolute EBI difference, and the "
            "top-5 communes."
        ),
        "n_variants": 1 + len(CANONICAL_INDICATORS),
        "n_indicators": len(CANONICAL_INDICATORS),
        "most_influential": influence_df.iloc[0].to_dict(),
        "least_influential": influence_df.iloc[-1].to_dict(),
        "top5_stability": dict(
            sorted(top5_counts.items(), key=lambda kv: -kv[1])
        ),
        "influence_table": influence,
    }
    out_json = DATA_DIR / "ebi_sensitivity.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Wrote: {out_json}")


if __name__ == "__main__":
    main()
