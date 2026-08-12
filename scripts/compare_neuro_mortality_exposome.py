"""Correlate neuro-sanitary mortality outcomes with exposome indicators."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome import config as exposome_config  # noqa: E402
from exposome.neuro_mortality import compute_exposome_correlations  # noqa: E402

app = typer.Typer(help="Compare neuro-sanitary mortality outcomes against the exposome master table.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Write a correlation table between mortality outcomes and exposome features."""
    cfg = exposome_config.load_config(city)
    mort_cfg = cfg["neuro_mortality"]
    years = [int(y) for y in mort_cfg["years"]]
    out_dir = Path(out_dir)

    mortality_path = out_dir / f"{city}_neuro_mortality_{min(years)}_{max(years)}.csv"
    master_path = out_dir / f"{city}_exposome_master.csv"
    if not mortality_path.exists():
        raise FileNotFoundError(f"Missing mortality comparator: {mortality_path}")
    if not master_path.exists():
        raise FileNotFoundError(f"Missing master exposome table: {master_path}")

    mortality = pd.read_csv(mortality_path)
    master = pd.read_csv(master_path)
    exposures = list(mort_cfg["comparison"]["exposures"])
    outcomes = list(mort_cfg["comparison"]["outcomes"])
    covariates = list(mort_cfg["comparison"]["covariates"])

    result = compute_exposome_correlations(
        mortality_df=mortality,
        master_df=master,
        exposures=exposures,
        outcomes=outcomes,
        covariates=covariates,
    )

    csv_path = out_dir / f"{city}_neuro_mortality_exposome_correlations.csv"
    meta_path = out_dir / f"{city}_neuro_mortality_exposome_correlations_metadata.json"
    result.to_csv(csv_path, index=False)
    meta_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "city": city,
                "mortality_source": mortality_path.name,
                "master_source": master_path.name,
                "exposures": exposures,
                "outcomes": outcomes,
                "covariates": covariates,
                "correlation_methods": [
                    "spearman",
                    "pearson",
                    "kendall",
                    "partial_spearman",
                ],
                "multiple_testing_correction": "benjamini_hochberg_fdr",
                "fdr_family": "all outcome x exposure tests within this table, separately by method",
                "n_rows": int(len(result)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    app()
