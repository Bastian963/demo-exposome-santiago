"""Generate a four-panel precipitation exposome figure.

Output: ``figures/precipitation_santiago_4panel.png``. Panels:
  1. ``precip_annual_mean_mm`` — chronic annual rainfall.
  2. ``precip_wet_day_pct`` — wet-day frequency (>=1 mm).
  3. ``precip_rx5day_mm`` — annual maximum 5-day total (heavy-rain proxy).
  4. ``precip_extremes_index`` — composite 0-100 percentile index.

Same pattern as ``scripts/plot_climate_heat_maps.py`` /
``scripts/plot_wildfire_maps.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import typer  # noqa: E402

app = typer.Typer(help="Plot 4-panel precipitation choropleth for all 52 communes.")


@app.command()
def run(
    geojson_path: Path = typer.Option(
        Path("data/processed/santiago_precipitation_chirps_2015_2024.geojson"),
        help="Canonical precipitation layer GeoJSON",
    ),
    out_path: Path = typer.Option(
        Path("figures/precipitation_santiago_4panel.png"),
        help="Output PNG path",
    ),
) -> None:
    """Render the 4-panel figure."""
    if not geojson_path.exists():
        raise FileNotFoundError(
            f"Missing {geojson_path}. Run scripts/run_precipitation.py first."
        )

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    axes = axes.flatten()

    panels = [
        (
            "precip_annual_mean_mm",
            "Precipitación anual media [mm]",
            "Blues",
        ),
        (
            "precip_wet_day_pct",
            "Días húmedos (>=1 mm) [%]",
            "PuBuGn",
        ),
        (
            "precip_rx5day_mm",
            "Máximo anual de 5 días consecutivos [mm]",
            "YlGnBu",
        ),
        (
            "precip_extremes_index",
            "Índice compuesto de extremos de lluvia [0-100]",
            "magma",
        ),
    ]

    for ax, (column, title, cmap) in zip(axes, panels):
        gdf.plot(
            column=column,
            cmap=cmap,
            linewidth=0.3,
            edgecolor="white",
            ax=ax,
            legend=True,
            legend_kwds={"shrink": 0.65, "label": column},
        )
        ax.set_title(title)
        ax.axis("off")

    fig.suptitle(
        "Exposoma de precipitación - Región Metropolitana de Santiago\n"
        "CHIRPS diario 2015-2024, estadísticas comunales",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    app()
