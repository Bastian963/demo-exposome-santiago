"""Compare exposome burden vs neurological outcomes (DEIS).

Joins the Environmental Burden Index (EBI) and selected exposome
indicators against the DEIS neurological outcomes (mortality
2018-2022, hospitalizations 2006) and computes:

1. Per-outcome Spearman correlations vs EBI / canonical indicators.
2. Per-commune scatter: EBI vs crude/age-adjusted rates.
3. Heatmap of correlation matrix (EBI + 14 canonical indicators
   x 15 outcomes).
4. JSON summary with significant (|rho| > 0.3, p < 0.05) pairs.

This script is **descriptive, not causal**. It is meant to
support a **signal-detection** exercise to identify which
exposome axes co-vary with neurological outcomes at the
commune level.

Outputs
-------
- ``data/processed/exposome_vs_neuro.json`` (summary)
- ``data/processed/exposome_vs_neuro.csv`` (all 210 pairs)
- ``data/processed/exposome_vs_neuro_significant.csv`` (|rho|>0.3, p<0.05)
- ``figures/exposome_vs_neuro_heatmap.png``
- ``figures/exposome_vs_neuro_scatter.png`` (4 panels: EBI vs
  mortality all_cause, EBI vs dementia mortality, EBI vs
  cerebrovascular hosp, EBI vs mental_all hosp)
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

# Canonical exposome indicators (subset of the 20 used in EBI).
# 14 indicators covering all exposome pillars, with their
# direction sign and a short display label.
EXPOSOME_AXES: list[tuple[str, str, str]] = [
    ("EBI", "ebi_score", "Environmental Burden Index"),
    ("PM2.5", "pm25_mean", "PM2.5 (ACAG)"),
    ("NO2", "no2_surface_ug_m3", "NO2 surface (sat)"),
    ("ALAN", "alan_radiance_mean", "ALAN radiance"),
    ("Noise", "noise_combined_pct", "Noise (combined %)"),
    ("Heat", "heat_exposure_index", "Heat exposure"),
    ("Green", "green_cover_pct_ndvi", "Greenspace NDVI"),
    ("Walk", "walk_index", "Walkability"),
    ("Transit", "transit_index", "Transit accessibility"),
    ("Health", "health_n_primary_care", "Primary care density"),
    ("Pobreza", "pobreza_pct", "Pobreza %"),
    ("NSE", "nse_index", "NSE index"),
    ("Hacinam.", "hacinamiento_phh", "Hacinamiento"),
    ("HeavyM", "hm_index", "Heavy metals index"),
]

# (display label, mortality column, hospitalizations column).
# "NA" means the column is not available for that outcome.
OUTCOMES: list[tuple[str, str, str]] = [
    ("mort_all_cause", "mortality_rate_age_adjusted_per_100k", "NA"),
    ("mort_alzheimer", "mortality_rate_age_adjusted_per_100k", "NA"),
    ("mort_dementia", "mortality_rate_age_adjusted_per_100k", "NA"),
    ("mort_cerebrovasc", "mortality_rate_age_adjusted_per_100k", "NA"),
    ("mort_parkinson", "mortality_rate_age_adjusted_per_100k", "NA"),
    ("hosp_all_cause", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_dementia", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_alzheimer", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_cerebrovasc", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_mental_all", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_anxiety", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_mood", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_psychosis", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_substance", "NA", "hospital_rate_age_adjusted_per_100k"),
    ("hosp_parkinson", "NA", "hospital_rate_age_adjusted_per_100k"),
]


def _load_ebi() -> pd.DataFrame:
    csv = DATA_DIR / "environmental_burden_index.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Run scripts/analyze_cross_layer.py first ({csv})")
    return pd.read_csv(csv)


def _load_master() -> pd.DataFrame:
    """Raw per-commune exposome indicators (EBI only stores percentile-transformed
    `pct_*` versions of these, not the raw columns EXPOSOME_AXES names)."""
    csv = DATA_DIR / "santiago_exposome_master.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Missing master exposome table ({csv})")
    return pd.read_csv(csv)


def _load_mortality() -> pd.DataFrame:
    csv = DATA_DIR / "santiago_neuro_mortality_2018_2022.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Run scripts/run_neuro_mortality.py first ({csv})")
    return pd.read_csv(csv)


def _load_hospitalizations() -> pd.DataFrame:
    csv = DATA_DIR / "santiago_neuro_hospitalizations_2006_2006.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Run scripts/run_neuro_hospitalizations.py first ({csv})")
    return pd.read_csv(csv)


def _outcomes_to_wide(neuro_long: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Pivot a long-format DEIS dataframe to wide: name x outcome."""
    out = neuro_long.pivot_table(
        index="name", columns="outcome", values=value_col, aggfunc="first",
    )
    out.columns = [f"{c}_{value_col}" for c in out.columns]
    return out.reset_index()


def _spearman_with_pvalues(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Spearman rho and two-sided p-value, robust to NaN and ties."""
    valid = x.notna() & y.notna()
    if valid.sum() < 10:
        return float("nan"), float("nan")
    rho, p = spearmanr(x[valid], y[valid])
    return float(rho), float(p)


def _compute_correlations(
    ebi: pd.DataFrame,
    master: pd.DataFrame,
    mort: pd.DataFrame,
    hosp: pd.DataFrame,
) -> pd.DataFrame:
    """For each (exposome axis, outcome) pair compute Spearman rho + p."""
    mort_wide = _outcomes_to_wide(
        mort, "mortality_rate_age_adjusted_per_100k",
    )
    hosp_wide = _outcomes_to_wide(
        hosp, "hospital_rate_age_adjusted_per_100k",
    )
    raw_axis_cols = [col for _, col, _ in EXPOSOME_AXES if col != "ebi_score"]
    combined = (
        ebi[["name", "ebi_score"]]
        .merge(master[["name"] + raw_axis_cols], on="name", how="left")
        .merge(mort_wide, on="name", how="left")
        .merge(hosp_wide, on="name", how="left")
    )

    rows: list[dict] = []
    for axis_label, axis_col, axis_full_label in EXPOSOME_AXES:
        if axis_col not in combined.columns:
            raise KeyError(
                f"Axis '{axis_label}' column '{axis_col}' not found in EBI or master "
                "table -- fix EXPOSOME_AXES rather than silently falling back."
            )
        x = combined[axis_col]
        for outcome_label, mort_col, hosp_col in OUTCOMES:
            if mort_col != "NA":
                target_col = f"{outcome_label.replace('mort_', '')}_{mort_col}"
            elif hosp_col != "NA":
                target_col = f"{outcome_label.replace('hosp_', '')}_{hosp_col}"
            else:
                continue
            if target_col not in combined.columns:
                continue
            y = combined[target_col]
            rho, p = _spearman_with_pvalues(x, y)
            kind = "mortality" if mort_col != "NA" else "hospitalization"
            outcome_short = (
                outcome_label.replace("mort_", "").replace("hosp_", "")
            )
            rows.append(
                {
                    "axis": axis_label,
                    "axis_col": axis_col,
                    "axis_full_label": axis_full_label,
                    "outcome": outcome_short,
                    "outcome_kind": kind,
                    "rho": round(rho, 4) if not np.isnan(rho) else None,
                    "p_value": round(p, 4) if not np.isnan(p) else None,
                    "n": int(x.notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def _plot_heatmap(corr_df: pd.DataFrame, out_path: Path) -> None:
    """Heatmap of Spearman rho: axes (rows) x outcomes (cols)."""
    pivot = corr_df.pivot_table(
        index="axis", columns="outcome", values="rho", aggfunc="first",
    )
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(pivot.values, cmap="RdBu_r", vmin=-0.6, vmax=0.6)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=8.5)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if not np.isnan(v):
                color = "white" if abs(v) > 0.35 else "black"
                ax.text(
                    j, i, f"{v:+.2f}", ha="center", va="center",
                    color=color, fontsize=7,
                )
    cbar = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.04)
    cbar.set_label("Spearman rho", fontsize=9)
    ax.set_title(
        "Exposome axes vs neurological outcomes (DEIS age-adjusted rates)",
        fontsize=10.5,
    )
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _plot_scatter(combined: pd.DataFrame, out_path: Path) -> None:
    """4-panel scatter: EBI vs 4 selected outcomes."""
    panels = [
        ("all_cause_mortality_rate_age_adjusted_per_100k", "Mortality (all cause)"),
        ("dementia_mortality_rate_age_adjusted_per_100k", "Dementia mortality"),
        ("cerebrovasc_hospital_rate_age_adjusted_per_100k", "Cerebrovasc hospitalizations"),
        ("mental_all_hospital_rate_age_adjusted_per_100k", "Mental health hospitalizations"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4))
    for ax, (col, title) in zip(axes, panels):
        if col not in combined.columns:
            ax.set_title(f"{title}\n(no data)", fontsize=9)
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        x = combined["ebi_score"]
        y = combined[col]
        valid = x.notna() & y.notna()
        if valid.sum() < 5:
            ax.set_title(f"{title}\n(n<5)", fontsize=9)
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        rho, p = spearmanr(x[valid], y[valid])
        ax.scatter(x[valid], y[valid], s=42, alpha=0.7, edgecolor="white")
        z = np.polyfit(x[valid], y[valid], 1)
        xs = np.linspace(x[valid].min(), x[valid].max(), 50)
        ax.plot(xs, np.polyval(z, xs), "k--", alpha=0.4, lw=1)
        ax.set_xlabel("EBI score", fontsize=8.5)
        ax.set_ylabel("Age-adj. rate (per 100k)", fontsize=8.5)
        ax.set_title(f"{title}\nrho={rho:+.2f}, p={p:.3f}", fontsize=9)
    plt.suptitle("EBI vs DEIS neurological outcomes (commune level)", y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    print("Loading EBI + master exposome table + DEIS outcomes...")
    ebi = _load_ebi()
    master = _load_master()
    mort = _load_mortality()
    hosp = _load_hospitalizations()

    print("Computing Spearman correlations across 14 axes x 15 outcomes...")
    corr_df = _compute_correlations(ebi, master, mort, hosp)
    corr_csv = DATA_DIR / "exposome_vs_neuro.csv"
    corr_df.to_csv(corr_csv, index=False)
    print(f"  Wrote: {corr_csv} ({len(corr_df)} pairs)")

    significant = corr_df[
        (corr_df["rho"].abs() > 0.3) & (corr_df["p_value"] < 0.05)
    ].copy()
    sig_csv = DATA_DIR / "exposome_vs_neuro_significant.csv"
    significant.to_csv(sig_csv, index=False)
    print(f"  Significant pairs (|rho|>0.3, p<0.05): {len(significant)}")
    print(f"  Wrote: {sig_csv}")

    print("Plotting heatmap + 4-panel scatter...")
    _plot_heatmap(corr_df, FIGURES_DIR / "exposome_vs_neuro_heatmap.png")
    print(f"  Saved: {FIGURES_DIR / 'exposome_vs_neuro_heatmap.png'}")

    mort_wide = _outcomes_to_wide(
        mort, "mortality_rate_age_adjusted_per_100k",
    )
    hosp_wide = _outcomes_to_wide(
        hosp, "hospital_rate_age_adjusted_per_100k",
    )
    combined = (
        ebi[["name", "ebi_score"]]
        .merge(mort_wide, on="name", how="left")
        .merge(hosp_wide, on="name", how="left")
    )
    _plot_scatter(combined, FIGURES_DIR / "exposome_vs_neuro_scatter.png")
    print(f"  Saved: {FIGURES_DIR / 'exposome_vs_neuro_scatter.png'}")

    top_pairs = (
        corr_df.dropna(subset=["rho"])
        .assign(abs_rho=lambda d: d["rho"].abs())
        .sort_values("abs_rho", ascending=False)
        .head(20)[["axis", "outcome", "outcome_kind", "rho", "p_value"]]
        .to_dict(orient="records")
    )
    sig_per_axis = (
        significant.groupby("axis").size().to_dict()
    )
    sig_per_outcome = (
        significant.groupby(["outcome", "outcome_kind"]).size().to_dict()
    )
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_axes": len(EXPOSOME_AXES),
        "n_outcomes": len(OUTCOMES),
        "n_total_pairs": len(corr_df),
        "n_significant_pairs": int(len(significant)),
        "axes": [a[0] for a in EXPOSOME_AXES],
        "outcomes": [o[0] for o in OUTCOMES],
        "top_20_abs_rho_pairs": top_pairs,
        "significant_per_axis": sig_per_axis,
        "significant_per_outcome": {
            f"{o[0]}_{o[1]}": c for o, c in sig_per_outcome.items()
        },
    }
    summary_path = DATA_DIR / "exposome_vs_neuro.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote: {summary_path}")
    print(f"  Done. {len(significant)} significant pairs detected.")


if __name__ == "__main__":
    main()
