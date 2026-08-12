"""Generate per-year PM2.5 annual averages for Santiago communes.

Uses the ACAG V6.GL.02 annual PM2.5 product from Google Earth Engine
(sat-io open-datasets catalog). Same source as the multi-year average
in scripts/run_air_quality.py, but outputs one CSV per year.

Output:
  data/processed/santiago_pm25_acag_{2015..2022}.csv

Usage:
  mamba activate exposome
  earthengine authenticate
  python scripts/generate_pm25_annual.py

Requires:
  - GEE authentication (earthengine authenticate)
  - Internet connection
  - The pipeline already in src/exposome/
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import ee
import geopandas as gpd
import pandas as pd
import typer

from exposome import config as cfg
from exposome.gee import init_gee, image_to_stats  # noqa: E402

app = typer.Typer(help="Generate per-year PM2.5 annual averages via GEE.")

ASSET = "projects/sat-io/open-datasets/GLOBAL-SATELLITE-PM25/ANNUAL"
YEARS = list(range(2015, 2023))  # 2015-2022 (8 years)


@app.command()
def main(
    city: str = typer.Option("santiago", help="City config name"),
    project: str = typer.Option("exposome-api", help="GEE project ID"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Fetch annual PM2.5 for each year and reduce to communes."""
    init_gee(project)
    print(f"GEE initialized (project={project})")

    # Load commune boundaries from the config.
    city_cfg = cfg.get_city(city)
    communes_path = REPO_ROOT / city_cfg.boundaries
    if not communes_path.exists():
        typer.echo(f"ERROR: commune boundaries not found at {communes_path}", err=True)
        raise typer.Exit(code=1)
    communes = gpd.read_file(communes_path)
    print(f"Loaded {len(communes)} communes from {communes_path.name}")

    out_dir.mkdir(parents=True, exist_ok=True)

    for year in YEARS:
        out_path = out_dir / f"santiago_pm25_acag_{year}.csv"
        if out_path.exists():
            print(f"  SKIP {year}: {out_path.name} already exists")
            continue
        print(f"Processing {year}...")
        try:
            col = (
                ee.ImageCollection(ASSET)
                .filterDate(f"{year}-01-01", f"{year}-12-31")
                .select([0])
            )
            img = col.mean().rename("pm25")
            stats = image_to_stats(img, communes, "pm25")
            stats.to_csv(out_path, index=False)
            n = len(stats)
            mean_val = stats["pm25"].mean() if "pm25" in stats.columns else "n/a"
            print(f"  Wrote: {out_path.relative_to(REPO_ROOT)} ({n} communes, mean={mean_val:.2f})")
        except Exception as e:
            print(f"  ERROR {year}: {e}")
            continue

    print(f"\nDone. Output: {out_dir.relative_to(REPO_ROOT)}")
    print("Next: python scripts/export_webapp_master.py to copy annual CSVs to webapp.")


if __name__ == "__main__":
    app()
