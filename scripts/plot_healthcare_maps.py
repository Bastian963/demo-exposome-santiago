"""Generate choropleth maps for the healthcare access layer.

This script can read either the standalone healthcare GeoJSON
(``santiago_healthcare_access.geojson``) or the master exposome GeoJSON
(``santiago_exposome_master.geojson``). When the master file is used, it also
plots health-accessibility-to-population ratios such as inhabitants per
hospital or per primary-care facility.
"""
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
        Path("data/processed/santiago_exposome_master.geojson"),
        help="GeoJSON to plot (healthcare access or master exposome)",
    ),
    out_dir: Path = typer.Option(Path("figures"), help="Output directory for PNGs"),
) -> None:
    """Generate choropleth maps from a healthcare or master GeoJSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(geojson)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    # Detect whether we are reading the master file (prefixed columns) or the
    # standalone healthcare access file.
    is_master = "health_n_primary_care" in gdf.columns
    prefix = "health_" if is_master else ""

    # Count columns are prefixed with ``health_`` in the master, but distance
    # and network-distance columns are not.
    def count_col(name: str) -> str:
        return f"{prefix}{name}"

    def dist_col(name: str) -> str:
        return name if is_master else f"{prefix}{name}"

    plots = [
        (
            count_col("n_primary_care"),
            "Atención primaria: número de establecimientos",
            "healthcare_n_primary_care_map.png",
            "YlGn",
            "n_primary_care",
        ),
        (
            dist_col("mean_nearest_primary_care_m"),
            "Atención primaria: distancia media (m)",
            "healthcare_mean_primary_care_distance_map.png",
            "YlOrRd",
            "metres",
        ),
        (
            count_col("n_hospital"),
            "Hospitales: número de establecimientos",
            "healthcare_n_hospital_map.png",
            "Blues",
            "n_hospital",
        ),
        (
            dist_col("mean_nearest_hospital_m"),
            "Hospitales: distancia media (m)",
            "healthcare_mean_hospital_distance_map.png",
            "Reds",
            "metres",
        ),
        (
            count_col("n_total"),
            "Total establecimientos de salud",
            "healthcare_n_total_map.png",
            "viridis",
            "n_total",
        ),
    ]

    network_col = dist_col("mean_nearest_primary_care_network_m")
    if network_col in gdf.columns:
        plots.append(
            (
                network_col,
                "Atención primaria: distancia media por red vial (m)",
                "healthcare_mean_primary_care_network_distance_map.png",
                "OrRd",
                "metres",
            )
        )

    # Health-to-population ratios (only available in the master file).
    ratio_plots = [
        (
            count_col("inhabitants_per_primary_care"),
            "Habitantes por establecimiento de atención primaria",
            "healthcare_ratio_inhabitants_per_primary_care_map.png",
            "RdYlGn_r",
            "habitantes / APS",
        ),
        (
            count_col("inhabitants_per_hospital"),
            "Habitantes por hospital",
            "healthcare_ratio_inhabitants_per_hospital_map.png",
            "RdYlGn_r",
            "habitantes / hospital",
        ),
        (
            count_col("inhabitants_per_clinic"),
            "Habitantes por clínica",
            "healthcare_ratio_inhabitants_per_clinic_map.png",
            "RdYlGn_r",
            "habitantes / clínica",
        ),
        (
            count_col("inhabitants_per_public_facility"),
            "Habitantes por establecimiento público",
            "healthcare_ratio_inhabitants_per_public_facility_map.png",
            "RdYlGn_r",
            "habitantes / público",
        ),
        (
            count_col("inhabitants_per_private_facility"),
            "Habitantes por establecimiento privado",
            "healthcare_ratio_inhabitants_per_private_facility_map.png",
            "RdYlGn_r",
            "habitantes / privado",
        ),
        (
            count_col("inhabitants_per_facility"),
            "Habitantes por establecimiento de salud (total)",
            "healthcare_ratio_inhabitants_per_facility_map.png",
            "RdYlGn_r",
            "habitantes / total",
        ),
    ]

    for column, title, filename, cmap, legend_label in ratio_plots:
        if column in gdf.columns:
            plots.append((column, title, filename, cmap, legend_label))


    for column, title, filename, cmap, legend_label in plots:
        _plot_choropleth(
            gdf, column, title, out_dir / filename, cmap=cmap, legend_label=legend_label
        )

    print(f"\nGenerated {len(plots)} maps in {out_dir}")


if __name__ == "__main__":
    app()
