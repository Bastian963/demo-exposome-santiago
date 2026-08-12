"""Publication-quality figure for the neuro-sanitary outcome comparators.

Reads `santiago_neuro_mortality_2018_2022.csv` and
`santiago_neuro_hospitalizations_2006_2006.csv` and produces a 4-panel figure
that contrasts commune-level outcomes against two exposome indicators.

Panels:
  A) Choropleth: age-adjusted all-cause mortality rate (per 100k, 2018-2022).
  B) Choropleth: age-adjusted all-cause hospitalization rate (per 100k, 2006).
  C) Scatter: all-cause mortality vs pm25_pop_weighted, with NSE overlay.
  D) Scatter: all-cause hospitalization vs nse_index (sanity check: the
     mortality-hi/NSE-lo vs hospitalization-hi/NSE-hi ecological paradox).

NOTE: hospitalization rates cover only 2006 and mortality covers 2018-2022.
The figure is an ecological comparator visual diagnostic, not a publication-
quality association plot. The temporal mismatch is documented in
`docs/neuro_outcomes_methodology.md` and in
`data/processed/santiago_neuro_hospitalizations_2006_2006_metadata.json`.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
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

CMAP_MORTALITY = "YlOrRd"
CMAP_HOSPITAL = "YlGnBu"


def _load_outcomes() -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    mort = pd.read_csv(DATA_DIR / "santiago_neuro_mortality_2018_2022.csv")
    hosp = pd.read_csv(DATA_DIR / "santiago_neuro_hospitalizations_2006_2006.csv")
    master = pd.read_csv(MASTER_CSV)
    gdf = gpd.read_file(DATA_DIR / "santiago_exposome_master.geojson")
    gdf = gdf[["name", "geometry"]].merge(master, on="name", how="left")
    return mort, hosp, gdf


def _choropleth(ax, gdf, col, cmap, title, unit, vmin=None, vmax=None) -> None:
    vals = gdf[col].astype(float)
    if vmin is None:
        vmin = float(vals.min())
    if vmax is None:
        vmax = float(vals.max())
    norm = Normalize(vmin=vmin, vmax=vmax)
    for _, row in gdf.iterrows():
        v = float(row[col])
        color = plt.get_cmap(cmap)(norm(v))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=unit)
    ax.set_title(title)
    ax.set_axis_off()


def _scatter_mortality_vs_pm25(ax, gdf) -> None:
    valid = gdf.dropna(subset=["mortality_rate_all_cause_per_100k", "pm25_pop_weighted"])
    if len(valid) < 5:
        ax.text(0.5, 0.5, "data not available", transform=ax.transAxes, ha="center")
        return
    x = valid["pm25_pop_weighted"].astype(float)
    y = valid["mortality_rate_all_cause_per_100k"].astype(float)
    r, p = spearmanr(x, y)
    colors = plt.get_cmap("viridis")(Normalize()(valid["nse_index"].astype(float)))
    ax.scatter(x, y, c=valid["nse_index"].astype(float), cmap="viridis",
               s=42, alpha=0.85, edgecolor="white", linewidth=0.4)
    m, b = np.polyfit(x, y, 1)
    xr = np.linspace(x.min(), x.max(), 100)
    ax.plot(xr, m * xr + b, color="#c33", lw=1.2, ls="--", alpha=0.7)
    pstr = "< 0.001" if p < 0.001 else f"= {p:.3f}"
    ax.set_title(
        f"Mortalidad (2018-2022) vs PM2.5  (Spearman r = {r:.2f}, p {pstr})"
    )
    ax.set_xlabel("PM2.5 poblacional (ug/m3)")
    ax.set_ylabel("Mortalidad ajustada por edad (por 100k)")


def _scatter_hosp_vs_nse(ax, gdf) -> None:
    valid = gdf.dropna(subset=["hospital_rate_all_cause_per_100k", "nse_index"])
    if len(valid) < 5:
        ax.text(0.5, 0.5, "data not available", transform=ax.transAxes, ha="center")
        return
    x = valid["nse_index"].astype(float)
    y = valid["hospital_rate_all_cause_per_100k"].astype(float)
    r, p = spearmanr(x, y)
    ax.scatter(x, y, c=valid["nse_index"].astype(float), cmap="plasma",
               s=42, alpha=0.85, edgecolor="white", linewidth=0.4)
    m, b = np.polyfit(x, y, 1)
    xr = np.linspace(x.min(), x.max(), 100)
    ax.plot(xr, m * xr + b, color="#c33", lw=1.2, ls="--", alpha=0.7)
    pstr = "< 0.001" if p < 0.001 else f"= {p:.3f}"
    ax.set_title(
        f"Hospitalizacion (2006) vs NSE  (Spearman r = {r:.2f}, p {pstr})"
    )
    ax.set_xlabel("NSE index (mayor = mejor posicion socioeconomica)")
    ax.set_ylabel("Hospitalizacion ajustada por edad (por 100k)")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    mort, hosp, gdf = _load_outcomes()

    mort_all = mort[mort["outcome"] == "all_cause"][
        ["name", "mortality_rate_age_adjusted_per_100k"]
    ].rename(columns={"mortality_rate_age_adjusted_per_100k": "mortality_rate_all_cause_per_100k"})
    hosp_all = hosp[hosp["outcome"] == "all_cause"][
        ["name", "hospital_rate_age_adjusted_per_100k"]
    ].rename(columns={"hospital_rate_age_adjusted_per_100k": "hospital_rate_all_cause_per_100k"})

    gdf = gdf.merge(mort_all, on="name", how="left").merge(hosp_all, on="name", how="left")

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Comparadores neuro-sanitarios — Region Metropolitana de Santiago\n"
        "Mortalidad DEIS 2018-2022  /  Hospitalizacion DEIS 2006 (unico ano disponible)\n"
        "Comparacion NO contemporanea — ver docs/neuro_outcomes_methodology.md",
        fontsize=11,
    )

    _choropleth(
        axes[0, 0], gdf, "mortality_rate_all_cause_per_100k", CMAP_MORTALITY,
        "A)  Mortalidad ajustada por edad, todas las causas (2018-2022)",
        "por 100k",
    )
    _choropleth(
        axes[0, 1], gdf, "hospital_rate_all_cause_per_100k", CMAP_HOSPITAL,
        "B)  Hospitalizacion ajustada por edad, todas las causas (2006)",
        "por 100k",
    )
    _scatter_mortality_vs_pm25(axes[1, 0], gdf)
    _scatter_hosp_vs_nse(axes[1, 1], gdf)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIGURES_DIR / "neuro_outcomes_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
