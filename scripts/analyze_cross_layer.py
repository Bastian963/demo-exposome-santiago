"""Cross-layer analysis over the master exposome table.

Reads `data/processed/santiago_exposome_master.csv` (52 communes x
~276 columns) and produces a compact set of **derived** artefacts
that summarise how the 13+ exposome layers relate to each other:

Outputs
-------
1. `data/processed/cross_layer_summary.json`
   Top/bottom 5 communes per canonical indicator; EBI top/bottom 5;
   hotspot list (communes with EBI > p75 AND high deprivacion);
   correlation pairs with |rho| > 0.5.
2. `data/processed/environmental_burden_index.csv`
   Per-commune EBI score (0-1), EBI rank, and the 6-8 component
   rank-percentile columns that feed into it.
3. `figures/correlation_matrix_cross_layer.png`
   Spearman correlation heatmap (20x20) across the canonical
   indicator set, with diverging RdBu_r colormap and rho values
   annotated.
4. `figures/socio_environmental_hotspots.png`
   4-panel scatter: EBI vs pobreza, EBI vs NSE quintil,
   PM2.5 vs pobreza, greenspace vs NSE.
5. `figures/environmental_burden_index.png`
   Choropleth of EBI score across the RM.

The script does NOT write EBI columns into the master; the master
remains a pure ingestion layer. EBI is a **derived** artefact that
can be regenerated at any time from the master, and is shipped as
a sidecar CSV + JSON so that downstream analyses can use it
without polluting the master schema.

Usage
-----
    python scripts/analyze_cross_layer.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
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

# Canonical indicator set: one column per layer, each representing
# the "headline" indicator of that layer. Where multiple plausible
# columns exist, we pick the most policy-relevant one.
# Direction:
#   +1 = higher value = higher burden (pollutant, noise, heat, etc.)
#   -1 = higher value = lower burden (greenspace, healthcare density)
# This sign convention lets us average rank-percentiles into EBI
# without further sign flipping.
CANONICAL_INDICATORS: list[tuple[str, str, int]] = [
    # (label, column, direction)
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


def _load_master() -> pd.DataFrame:
    csv = DATA_DIR / "santiago_exposome_master.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"Master exposome CSV not found: {csv}. "
            "Run scripts/build_master_exposome.py first."
        )
    return pd.read_csv(csv)


def _rank_percentile(s: pd.Series, direction: int) -> pd.Series:
    """Convert to [0, 1] rank-percentile, sign-adjusted by `direction`.

    direction=+1: higher raw value -> higher percentile (more burden).
    direction=-1: higher raw value -> lower percentile (less burden).
    """
    r = s.rank(pct=True, na_option="bottom")
    if direction == -1:
        r = 1.0 - r
    return r.fillna(0.5)


def _compute_ebi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the Environmental Burden Index (EBI).

    For each canonical indicator, convert to rank-percentile with
    direction-adjusted sign; EBI = mean across the available
    percentile columns.
    """
    used: list[str] = []
    pct_df = pd.DataFrame(index=df.index)
    for label, col, direction in CANONICAL_INDICATORS:
        if col in df.columns and df[col].notna().sum() >= 30:
            pct_col = f"pct_{col}"
            pct_df[pct_col] = _rank_percentile(df[col], direction)
            used.append(pct_col)
    ebi = pct_df.mean(axis=1) if used else pd.Series(np.nan, index=df.index)
    out = pd.DataFrame({
        "name": df["name"],
        "ebi_score": ebi.round(4),
        "ebi_rank": ebi.rank(ascending=False, method="average").round(1),
    })
    for c in used:
        out[c] = pct_df[c].round(4)
    return out, used


def _correlation_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Compute Spearman correlation matrix over the canonical set."""
    cols = [c for _, c, _ in CANONICAL_INDICATORS if c in df.columns]
    sub = df[cols].dropna(how="any")
    if len(sub) < 10:
        sub = df[cols].fillna(df[cols].median())
    corr = sub.corr(method="spearman")
    return corr, cols


def _strong_pairs(corr: pd.DataFrame, threshold: float = 0.5) -> list[dict]:
    """List of (i, j, rho) pairs with |rho| > threshold (upper triangle)."""
    pairs: list[dict] = []
    cols = corr.columns.tolist()
    labels = {c: l for l, c, _ in CANONICAL_INDICATORS}
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = float(corr.iloc[i, j])
            if abs(r) >= threshold:
                pairs.append({
                    "indicator_a": labels.get(cols[i], cols[i]),
                    "indicator_b": labels.get(cols[j], cols[j]),
                    "spearman_rho": round(r, 3),
                })
    pairs.sort(key=lambda p: -abs(p["spearman_rho"]))
    return pairs


def _hotspots(ebi: pd.DataFrame, df: pd.DataFrame) -> list[str]:
    """Communes with EBI > p75 AND high deprivacion (nse_quintil >= 4)."""
    if "nse_quintil" not in df.columns:
        return []
    ebi_thr = ebi["ebi_score"].quantile(0.75)
    mask = (ebi["ebi_score"] > ebi_thr) & (df["nse_quintil"] >= 4)
    return ebi.loc[mask, "name"].tolist()


def _double_burden_extended(ebi: pd.DataFrame, df: pd.DataFrame) -> list[str]:
    """Hotspots with stricter definition: EBI > p75 AND nse_quintil <= 2.

    Captures the "double burden" of high environmental exposure plus
    high socioeconomic deprivation (NSE quintil 1-2 = most deprived).
    """
    if "nse_quintil" not in df.columns:
        return []
    ebi_thr = ebi["ebi_score"].quantile(0.75)
    mask = (ebi["ebi_score"] > ebi_thr) & (df["nse_quintil"] <= 2)
    return ebi.loc[mask, "name"].tolist()


def _compute_double_burden(ebi: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Compute double-burden score combining EBI + NSE deprivation.

    db_score = 0.5 * ebi_score + 0.5 * (1 - nse_index normalized)
    where (1 - nse_index normalized) is the rank-percentile of
    (1 - nse_index) i.e. higher when nse_index is lower.

    The two halves are equal-weighted to avoid EBI dominance; tune
    by changing the alpha parameter.
    """
    out = ebi[["name", "ebi_score"]].copy()
    if "nse_index" not in df.columns:
        out["db_score"] = out["ebi_score"]
    else:
        deprivation = 1.0 - df["nse_index"]
        deprivation_pct = deprivation.rank(pct=True, na_option="bottom")
        out["db_score"] = (
            0.5 * out["ebi_score"] + 0.5 * deprivation_pct.fillna(0.5)
        ).round(4)
    out["db_rank"] = (
        out["db_score"].rank(ascending=False, method="average").round(1)
    )
    return out


def _compute_ebi_pca(
    df: pd.DataFrame, used_pct_cols: list[str],
) -> tuple[pd.DataFrame, int, float]:
    """Compute a PCA-weighted EBI that decorrelates the indicators.

    Uses the **original** canonical indicator columns from the master
    (not the rank-percentile versions), standardised. PC1 is
    retained if its eigenvalue > 1 (Kaiser criterion); the score is
    the rank-percentile of PC1 across communes.
    """
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    cols_present = [c for _, c, _ in CANONICAL_INDICATORS
                    if c in df.columns]
    if len(cols_present) < 2:
        empty = pd.DataFrame({
            "name": df.get("name", pd.Series(dtype=str)),
            "ebi_pca_score": 0.5,
            "ebi_pca_rank": 1.0,
        })
        return empty, 0, 0.0
    sub = df[cols_present].fillna(df[cols_present].median())
    features = StandardScaler().fit_transform(sub.values)
    n_components = min(8, features.shape[0], features.shape[1])
    pca = PCA(n_components=n_components, random_state=42)
    pca.fit(features)
    retained = int(sum(pca.explained_variance_ > 1.0))
    retained = max(retained, 1)
    pc1 = pca.transform(features)[:, 0]
    pc1_pct = pd.Series(pc1).rank(pct=True).values
    out = pd.DataFrame({
        "name": df["name"].values,
        "ebi_pca_score": np.round(pc1_pct, 4),
    })
    out["ebi_pca_rank"] = (
        out["ebi_pca_score"].rank(ascending=False, method="average").round(1)
    )
    variance_explained = float(
        pca.explained_variance_ratio_[:retained].sum()
    )
    return out, retained, variance_explained


def _compute_effective_dose(df: pd.DataFrame) -> pd.DataFrame:
    """Compute effective winter dose = pollutant * wind_calm_winter.

    Captures the **effective exposure** during the high-stagnation
    winter season by combining the chronic pollutant level with the
    fraction of winter hours with low wind (< 2 m/s). The
    product (rank-normalised) is the communes where the local dose
    is highest during winter stagnation.
    """
    out = pd.DataFrame({"name": df["name"].values})
    if "wind_calm_pct_winter" not in df.columns:
        out["effective_dose_mean"] = np.nan
        out["effective_dose_rank"] = np.nan
        return out
    calm = df["wind_calm_pct_winter"].fillna(df["wind_calm_pct_winter"].median())
    parts: list[pd.Series] = []
    pairs = [
        ("pm25_mean", "PM2.5"),
        ("no2_surface_ug_m3", "NO2"),
        ("o3_mean", "O3"),
    ]
    for col, _label in pairs:
        if col in df.columns:
            pollutant = df[col].fillna(df[col].median())
            pollutant_rank = pollutant.rank(pct=True)
            dose = pollutant_rank * calm
            parts.append(dose)
    if not parts:
        out["effective_dose_mean"] = np.nan
        out["effective_dose_rank"] = np.nan
        return out
    mean_dose = pd.concat(parts, axis=1).mean(axis=1)
    mean_dose_pct = mean_dose.rank(pct=True)
    out["effective_dose_mean"] = np.round(mean_dose_pct, 4)
    out["effective_dose_rank"] = (
        mean_dose_pct.rank(ascending=False, method="average").round(1)
    )
    return out


def _plot_pca_loadings(used_pct_cols: list[str], out: Path) -> None:
    """Heatmap of PC1 loadings on the canonical indicators."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
    cols_present = [c for _, c, _ in CANONICAL_INDICATORS
                    if c in master.columns]
    if len(cols_present) < 2:
        print("Skipped PCA loadings: insufficient canonical cols")
        return
    sub = master[cols_present].fillna(master[cols_present].median())
    features = StandardScaler().fit_transform(sub.values)
    pca = PCA(n_components=min(3, features.shape[1]), random_state=42)
    pca.fit(features)
    label_map = {c: l for l, c, _ in CANONICAL_INDICATORS}
    labels = [label_map.get(c, c) for c in cols_present]
    n_pc = pca.components_.shape[0]
    fig, ax = plt.subplots(figsize=(7 + n_pc, max(6, len(labels) * 0.4)))
    vmax = float(np.abs(pca.components_).max())
    im = ax.imshow(
        pca.components_.T, cmap="RdBu_r", vmin=-vmax, vmax=vmax,
        aspect="auto",
    )
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xticks(np.arange(n_pc))
    ax.set_xticklabels(
        [f"PC{i+1} ({100*pca.explained_variance_ratio_[i]:.1f}%)"
         for i in range(n_pc)], fontsize=9,
    )
    for i in range(len(labels)):
        for j in range(n_pc):
            val = pca.components_[j, i]
            color = "white" if abs(val) > 0.3 * vmax else "#333"
            ax.text(j, i, f"{val:+.2f}", ha="center", va="center",
                    color=color, fontsize=7.5)
    ax.set_title(
        f"PCA loadings sobre {len(labels)} indicadores canonicos",
        fontsize=10.5,
    )
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _plot_effective_dose_map(df: pd.DataFrame, ed: pd.DataFrame,
                             out: Path) -> None:
    """Choropleth + scatter of effective winter dose."""
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    if not geo.exists():
        return
    import geopandas as gpd
    gdf = gpd.read_file(geo)
    gdf = gdf[["name", "geometry"]].merge(ed, on="name", how="left")
    fig, axes = plt.subplots(1, 2, figsize=(14, 8),
                             gridspec_kw={"width_ratios": [1.2, 1]})
    fig.suptitle(
        "Dosis efectiva invierno — pollutant * wind_calm_winter\n"
        "Combina contaminacion cronica con la fraccion de horas invernales en calma",
        fontsize=10.5,
    )
    vals = gdf["effective_dose_mean"].astype(float)
    vmin, vmax = float(vals.min()), float(vals.max())
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    for _, row in gdf.iterrows():
        v = float(row["effective_dose_mean"])
        color = plt.get_cmap("YlOrRd")(norm(v))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=axes[0], color=color, edgecolor="white", linewidth=0.4,
        )
    sm = plt.cm.ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=axes[0], fraction=0.03, pad=0.02,
                 label="effective_dose (rank 0-1)")
    axes[0].set_title("A)  Effective winter dose (choropleth)", fontsize=10)
    axes[0].set_axis_off()

    # Scatter pm25 vs wind_calm_winter, color = effective_dose.
    if {"pm25_mean", "wind_calm_pct_winter"}.issubset(df.columns):
        s = df.merge(ed[["name", "effective_dose_mean"]], on="name").dropna()
        sc = axes[1].scatter(
            s["pm25_mean"], s["wind_calm_pct_winter"],
            c=s["effective_dose_mean"], cmap="YlOrRd", s=70,
            edgecolor="white", linewidth=0.5,
        )
        for _, r in s.iterrows():
            axes[1].annotate(
                r["name"],
                (r["pm25_mean"], r["wind_calm_pct_winter"]),
                fontsize=5.5, xytext=(3, 2), textcoords="offset points",
                color="#444",
            )
        plt.colorbar(sc, ax=axes[1], fraction=0.04, pad=0.02,
                     label="effective_dose (rank 0-1)")
    axes[1].set_xlabel("PM2.5 mean (ug/m3)")
    axes[1].set_ylabel("Wind calm winter (fraction < 2 m/s)")
    axes[1].set_title("B)  PM2.5 vs winter calma (color = effective dose)", fontsize=10)
    axes[1].grid(alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _plot_correlation_matrix(corr: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 9))
    cols = corr.columns.tolist()
    label_map = {c: l for l, c, _ in CANONICAL_INDICATORS}
    labels = [label_map.get(c, c) for c in cols]
    n = len(labels)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=8)
    ax.set_yticklabels(labels, fontsize=8)
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            color = "white" if abs(v) > 0.55 else "#333"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=color, fontsize=7)
    ax.set_title(
        "Matriz de correlacion Spearman — indicadores canonicos del exposome\n"
        "52 comunas, Region Metropolitana de Santiago",
        fontsize=10.5,
    )
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="rho Spearman")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _plot_hotspots(df: pd.DataFrame, ebi: pd.DataFrame, out: Path) -> None:
    if "nse_quintil" not in df.columns or "pobreza_pct" not in df.columns:
        print("Skipped hotspot scatter: missing nse_quintil or pobreza_pct")
        return
    merged = df.merge(ebi[["name", "ebi_score"]], on="name", how="left")
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle(
        "Hotspots socio-ambientales — Region Metropolitana de Santiago\n"
        "Cruce de burden ambiental (EBI) con privacion socioeconomica",
        fontsize=10.5,
    )

    panels = [
        (axes[0, 0], "ebi_score", "pobreza_pct",
         "A)  EBI vs Pobreza %",
         "EBI (rank-percentile, 0-1)", "Pobreza (%)"),
        (axes[0, 1], "ebi_score", "nse_quintil",
         "B)  EBI vs Quintil NSE (1=bajo, 5=alto)",
         "EBI (rank-percentile, 0-1)", "NSE quintil"),
        (axes[1, 0], "pm25_mean", "pobreza_pct",
         "C)  PM2.5 vs Pobreza %",
         "PM2.5 (ug/m3, ACAG)", "Pobreza (%)"),
        (axes[1, 1], "green_cover_pct_ndvi", "nse_quintil",
         "D)  Cobertura verde vs Quintil NSE",
         "Green cover NDVI (%)", "NSE quintil"),
    ]
    for ax, x, y, title, xl, yl in panels:
        if x not in merged.columns or y not in merged.columns:
            ax.set_axis_off()
            ax.text(0.5, 0.5, f"missing {x} or {y}", ha="center")
            continue
        s = merged[[x, y, "name"]].dropna()
        if s.empty:
            ax.set_axis_off()
            continue
        rho, p = spearmanr(s[x], s[y])
        ax.scatter(s[x], s[y], s=42, c="#3b6fb6", edgecolor="white",
                   alpha=0.85, linewidth=0.5)
        for _, r in s.iterrows():
            ax.annotate(r["name"], (r[x], r[y]), fontsize=5.5,
                        xytext=(3, 2), textcoords="offset points",
                        color="#444")
        ax.axhline(s[y].median(), color="#bbb", lw=0.6, ls="--")
        ax.axvline(s[x].median(), color="#bbb", lw=0.6, ls="--")
        ax.set_xlabel(xl, fontsize=9)
        ax.set_ylabel(yl, fontsize=9)
        ax.set_title(f"{title}\nrho = {rho:+.2f}  (p = {p:.3f}, n = {len(s)})",
                     fontsize=9)
        ax.grid(alpha=0.25)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _plot_ebi_choropleth(ebi: pd.DataFrame, out: Path) -> None:
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    if not geo.exists():
        print(f"Skipped EBI choropleth: missing {geo}")
        return
    import geopandas as gpd
    gdf = gpd.read_file(geo)
    gdf = gdf[["name", "geometry"]].merge(ebi, on="name", how="left")
    fig, ax = plt.subplots(figsize=(8, 9))
    vmin = float(gdf["ebi_score"].min())
    vmax = float(gdf["ebi_score"].max())
    norm = Normalize(vmin=vmin, vmax=vmax)
    for _, row in gdf.iterrows():
        v = float(row["ebi_score"])
        color = plt.get_cmap("YlOrRd")(norm(v))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    sm = plt.cm.ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02,
                 label="EBI (rank-percentile, 0-1)")
    top5 = ebi.sort_values("ebi_score", ascending=False).head(5)["name"].tolist()
    bot5 = ebi.sort_values("ebi_score", ascending=True).head(5)["name"].tolist()
    title = (
        "Environmental Burden Index (EBI) — Region Metropolitana de Santiago\n"
        f"Top 5: {', '.join(top5)}    Bottom 5: {', '.join(bot5)}"
    )
    ax.set_title(title, fontsize=10)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _top_bottom(ebi: pd.DataFrame, n: int = 5) -> dict:
    return {
        "top_n": ebi.sort_values("ebi_score", ascending=False)
            .head(n)[["name", "ebi_score", "ebi_rank"]]
            .to_dict(orient="records"),
        "bottom_n": ebi.sort_values("ebi_score", ascending=True)
            .head(n)[["name", "ebi_score", "ebi_rank"]]
            .to_dict(orient="records"),
    }


def _top_bottom_pca(ebi: pd.DataFrame, n: int = 5) -> dict:
    if "ebi_pca_score" not in ebi.columns:
        return {"top_n": [], "bottom_n": []}
    return {
        "top_n": ebi.sort_values("ebi_pca_score", ascending=False)
            .head(n)[["name", "ebi_pca_score", "ebi_pca_rank"]]
            .to_dict(orient="records"),
        "bottom_n": ebi.sort_values("ebi_pca_score", ascending=True)
            .head(n)[["name", "ebi_pca_score", "ebi_pca_rank"]]
            .to_dict(orient="records"),
    }


def _top_bottom_db(ebi: pd.DataFrame, n: int = 5) -> dict:
    if "db_score" not in ebi.columns:
        return {"top_n": [], "bottom_n": []}
    return {
        "top_n": ebi.sort_values("db_score", ascending=False)
            .head(n)[["name", "db_score", "db_rank"]]
            .to_dict(orient="records"),
        "bottom_n": ebi.sort_values("db_score", ascending=True)
            .head(n)[["name", "db_score", "db_rank"]]
            .to_dict(orient="records"),
    }


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    df = _load_master()
    if "name" not in df.columns:
        raise ValueError("master CSV missing 'name' column")

    ebi, used_pct_cols = _compute_ebi(df)

    # Phase F: double-burden index.
    db = _compute_double_burden(ebi, df)
    ebi = ebi.merge(db[["name", "db_score", "db_rank"]], on="name", how="left")

    # Phase A: PCA-weighted EBI.
    ebi_pca, n_components_pca, var_explained = _compute_ebi_pca(df, used_pct_cols)
    ebi = ebi.merge(ebi_pca, on="name", how="left")

    # Phase E: effective winter dose.
    ed = _compute_effective_dose(df)
    ebi = ebi.merge(ed, on="name", how="left")

    ebi_csv = DATA_DIR / "environmental_burden_index.csv"
    ebi.to_csv(ebi_csv, index=False)
    print(f"Wrote: {ebi_csv} ({len(ebi)} rows x {ebi.shape[1]} cols)")

    corr, corr_cols = _correlation_matrix(df)
    _plot_correlation_matrix(
        corr, FIGURES_DIR / "correlation_matrix_cross_layer.png"
    )
    _plot_hotspots(df, ebi, FIGURES_DIR / "socio_environmental_hotspots.png")
    _plot_ebi_choropleth(ebi, FIGURES_DIR / "environmental_burden_index.png")
    _plot_pca_loadings(used_pct_cols, FIGURES_DIR / "ebi_pca_loadings.png")
    _plot_effective_dose_map(df, ed, FIGURES_DIR / "effective_dose_winter_map.png")

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_communes": int(len(df)),
        "canonical_indicators": [
            {"label": l, "column": c, "direction": d}
            for l, c, d in CANONICAL_INDICATORS
        ],
        "used_pct_columns": used_pct_cols,
        "ebi_top_bottom": _top_bottom(ebi, n=5),
        "ebi_pca_top_bottom": _top_bottom_pca(ebi, n=5),
        "db_top_bottom": _top_bottom_db(ebi, n=5),
        "hotspots_high_burden_and_deprivation": _hotspots(ebi, df),
        "double_burden_top10": _double_burden_extended(ebi, df),
        "strong_correlations_abs_rho_ge_0.5": _strong_pairs(corr, 0.5),
        "pca_variance_explained": var_explained,
        "pca_n_components_retained": n_components_pca,
    }
    summary_path = DATA_DIR / "cross_layer_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote: {summary_path}")


if __name__ == "__main__":
    sys.exit(main())
