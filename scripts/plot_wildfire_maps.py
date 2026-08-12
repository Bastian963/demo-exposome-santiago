"""Generate a 4-panel wildfire (forest-fire) choropleth for all 52 communes.

Output: ``figures/wildfire_santiago_4panel.png``. Panels:
  1. ``fire_burned_pct_mean_annual`` — chronic burned-area load.
  2. ``fire_burn_years_count`` — recurrence (years of 10 with a burn).
  3. ``fire_exposure_index`` — composite 0-100 (sqrt-normalised, weighted).
  4. ``fire_brightness_max_k`` — max FIRMS T21 brightness (K); 0 = no detection.

Same pattern as ``scripts/plot_climate_heat_maps.py`` /
``scripts/plot_healthcare_maps.py``. Reads the canonical layer CSV + the
master GeoJSON (for geometry).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import typer  # noqa: E402

app = typer.Typer(help="Plot 4-panel wildfire choropleth for all 52 communes.")


@app.command()
def run(
    csv_path: Path = typer.Option(
        Path("data/processed/santiago_wildfire_2015_2024.csv"),
        help="Canonical wildfire layer CSV",
    ),
    geojson_path: Path = typer.Option(
        Path("data/processed/santiago_exposome_master.geojson"),
        help="Commune GeoJSON (for geometry, e.g. the master exposome GeoJSON)",
    ),
    out_path: Path = typer.Option(
        Path("figures/wildfire_santiago_4panel.png"),
        help="Output PNG path",
    ),
) -> None:
    """Render the 4-panel figure."""
    df = pd.read_csv(csv_path)
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf = gdf[["name", "geometry"]].merge(df, on="name", how="left")

    panels = [
        (
            "fire_burned_pct_mean_annual",
            "Area quemada media anual (% del area comunal)",
            "YlOrRd",
        ),
        (
            "fire_burn_years_count",
            "Anios con fuego (recurrencia, de 10)",
            "YlOrRd",
        ),
        (
            "fire_exposure_index",
            "Indice compuesto de exposicion a incendios (0-100)",
            "RdYlBu_r",
        ),
        (
            "fire_brightness_max_k",
            "Brillo FIRMS T21 maximo (K) — 0 = sin deteccion",
            "inferno",
        ),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    for ax, (col, title, cmap) in zip(axes.flat, panels):
        gdf.plot(
            column=col,
            ax=ax,
            legend=True,
            cmap=cmap,
            legend_kwds={"shrink": 0.6, "label": col},
            edgecolor="white",
            linewidth=0.3,
            missing_kwds={"color": "lightgrey", "label": "No data"},
        )
        ax.set_title(title, fontsize=12)
        ax.axis("off")

    fig.suptitle(
        "Exposoma — Incendios forestales (Santiago, 2015-2024)",
        fontsize=14,
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    app()
