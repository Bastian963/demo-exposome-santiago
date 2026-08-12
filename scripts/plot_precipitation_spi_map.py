"""4-panel summary figure for the precipitation_spi (drought) exposome layer.

Panels:
  A) Choropleth: drought_months_pct (% months in moderate drought).
  B) Choropleth: precip_trend_mm_per_decade (linear trend).
  C) Choropleth: spi_12_latest (most recent 12-month SPI).
  D) Choropleth: drought_max_duration_months (longest consecutive drought).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
FIGURES_DIR = REPO_ROOT / "figures"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    }
)


def main() -> None:
    geo = DATA_DIR / "santiago_precipitation_spi.geojson"
    if not geo.exists():
        raise FileNotFoundError(f"Missing {geo}; run scripts/run_precipitation_spi.py first.")
    gdf = gpd.read_file(geo)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    panels = [
        ("drought_months_pct", "Meses en sequía moderada (%)\n(SPI-3 < -1)", "YlOrRd", None, None, "%"),
        ("precip_trend_mm_per_decade", "Tendencia de precipitación\n(mm/década, OLS 2015-2024)", "RdBu", None, None, "mm/década"),
        ("spi_12_latest", "SPI-12 más reciente\n(estandarizado, media 0)", "BrBG", -3, 3, "σ"),
        ("drought_max_duration_months", "Sequía consecutiva máxima\n(meses con SPI-3 < -1)", "OrRd", None, None, "meses"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))
    for ax, (col, title, cmap, vmin, vmax, unit) in zip(axes.flatten(), panels):
        kw = dict(column=col, cmap=cmap, linewidth=0.3, edgecolor="white", ax=ax, legend=True)
        if vmin is not None:
            kw["vmin"] = vmin
        if vmax is not None:
            kw["vmax"] = vmax
        gdf.plot(legend_kwds={"label": unit, "shrink": 0.6}, **kw)
        ax.set_title(title)
        ax.axis("off")

    fig.suptitle(
        "Exposoma de sequía — Región Metropolitana de Santiago\n"
        "SPI (McKee 1993) sobre CHIRPS diario 2015–2024",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out = FIGURES_DIR / "precipitation_spi_santiago_4panel.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
