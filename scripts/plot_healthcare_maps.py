"""Generate choropleth maps for the healthcare access layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd
import matplotlib.pyplot as plt
import typer  # noqa: E402

app = typer.Typer(help="Plot healthcare access maps.")


def _plot_choropleth(
    gdf: gpd.GeoDataFrame,
    column: str,
    title: str,
    out_path: Path,
    cmap: str = "viridis",
    legend_label: str | None = None,
) -> None:
    """Plot a single choropleth map and save it."""
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    gdf.plot(
        column=column,
        ax=ax,
        legend=True,
        cmap=cmap,
        legend_kwds={
            "label": legend_label or column,
            "shrink": 0.5,
        },
        edgecolor="white",
        linewidth=0.3,
        missing_kwds={"color": "lightgrey", "label": "No data"},
    )
    ax.set_title(title, fontsize=14)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Wrote {out_path.name}")


@app.command()
def run(
    geojson: Path = typer.Option(
        Path("data/processed/santiago_healthcare_access.geojson"),
        help="Healthcare access GeoJSON to plot",
    ),
    out_dir: Path = typer.Option(Path("figures"), help="Output directory for PNGs"),
) -> None:
    """Generate choropleth maps from the healthcare access GeoJSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(geojson)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    plots = [
        (
            "n_primary_care",
            "Atención primaria: número de establecimientos",
            "healthcare_n_primary_care_map.png",
            "YlGn",
            "n_primary_care",
        ),
        (
            "mean_nearest_primary_care_m",
            "Atención primaria: distancia media (m)",
            "healthcare_mean_primary_care_distance_map.png",
            "YlOrRd",
            "metres",
        ),
        (
            "n_hospital",
            "Hospitales: número de establecimientos",
            "healthcare_n_hospital_map.png",
            "Blues",
            "n_hospital",
        ),
        (
            "mean_nearest_hospital_m",
            "Hospitales: distancia media (m)",
            "healthcare_mean_hospital_distance_map.png",
            "Reds",
            "metres",
        ),
        (
            "n_total",
            "Total establecimientos de salud",
            "healthcare_n_total_map.png",
            "viridis",
            "n_total",
        ),
    ]

    if "mean_nearest_primary_care_network_m" in gdf.columns:
        plots.append(
            (
                "mean_nearest_primary_care_network_m",
                "Atención primaria: distancia media por red vial (m)",
                "healthcare_mean_primary_care_network_distance_map.png",
                "OrRd",
                "metres",
            )
        )

    for column, title, filename, cmap, legend_label in plots:
        _plot_choropleth(
            gdf, column, title, out_dir / filename, cmap=cmap, legend_label=legend_label
        )

    print(f"\nGenerated {len(plots)} maps in {out_dir}")


if __name__ == "__main__":
    app()
