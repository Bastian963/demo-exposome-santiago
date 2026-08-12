"""Generate a 4-panel climate_heat choropleth covering all 52 communes.

Output: ``figures/climate_heat_santiago_4panel.png``. This complements
the legacy publication figure (``climate_heat_santiago_pub.png``) which
only labels 33 urban communes. The 4-panel view is the standard
inspection artefact for the layer audit.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import typer  # noqa: E402

app = typer.Typer(help="Plot 4-panel climate_heat choropleth for all 52 communes.")


@app.command()
def run(
    csv_path: Path = typer.Option(
        Path("data/processed/santiago_climate_heat_exposome_rm_santiago.csv"),
        help="Canonical climate_heat layer CSV",
    ),
    geojson_path: Path = typer.Option(
        Path("data/processed/santiago_climate_heat_exposome_rm_santiago.geojson"),
        help="Commune GeoJSON (for geometry)",
    ),
    out_path: Path = typer.Option(
        Path("figures/climate_heat_santiago_4panel.png"),
        help="Output PNG path",
    ),
) -> None:
    """Render the 4-panel figure."""
    df = pd_read_csv(csv_path) if (csv_path := Path(csv_path)).exists() else None
    if df is None:
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf = gdf[["name", "geometry"]].merge(df, on="name", how="left")

    panels = [
        ("tmean_annual_c", "Temperatura media anual (°C)", "YlOrRd"),
        ("hot_days_30c", "Días con tmax ≥ 30 °C", "YlOrRd"),
        ("tropical_nights_20c", "Noches tropicales (tmin ≥ 20 °C)", "YlOrRd"),
        ("heat_exposure_index", "Índice de exposición a calor (z compuesto)", "RdYlBu_r"),
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
        "Exposoma — Calor urbano y clima (Santiago, 2024)",
        fontsize=14,
        y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def pd_read_csv(path: Path) -> "pd.DataFrame":  # type: ignore[name-defined]
    import pandas as pd
    return pd.read_csv(path)


if __name__ == "__main__":
    app()
