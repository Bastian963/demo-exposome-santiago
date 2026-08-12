"""Build and analyse the DEIS 2011-2020 hospitalization outcome series.

This is local computation over already-downloaded files.  It does not contact
DEIS, INE, GEE, Open-Meteo, OSM or any other provider.
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome import config as exposome_config  # noqa: E402
from exposome.hospitalization_analytics import (  # noqa: E402
    ALL_OUTCOMES,
    CARDIORESPIRATORY_PRIMARY,
    NEUROPSYCHIATRIC_PRIMARY,
    aggregate_hospitalization_stream,
    archive_inventory,
    complete_cube_with_population,
    compute_annual_expected,
    compute_window_smr,
    fit_chronic_associations,
    fit_panel_ppml,
    load_ine_population_person_years,
    residual_morans_i,
    write_json,
)
from exposome.neuro_hospitalizations import resolve_source_paths  # noqa: E402


app = typer.Typer(help="DEIS hospitalizations x exposome analysis (local files only).")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _crosswalk() -> pd.DataFrame:
    path = REPO_ROOT / "data/reference/cl/santiago/santiago_communes/cut_crosswalk.csv"
    return pd.read_csv(path, dtype={"spatial_id": str}).rename(
        columns={"legacy_name": "name"}
    )


def _normalise_master(crosswalk: pd.DataFrame) -> pd.DataFrame:
    candidates = [
        REPO_ROOT / "data/processed/cl/santiago/santiago_communes/master.csv",
        REPO_ROOT / "data/processed/santiago_exposome_master.csv",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Missing exposome master; checked {candidates}")
    master = pd.read_csv(path)
    if "spatial_id" in master.columns:
        master["spatial_id"] = pd.to_numeric(master["spatial_id"], errors="coerce").astype(
            "Int64"
        ).astype(str)
        if "spatial_name" not in master.columns:
            master = master.merge(
                crosswalk[["spatial_id", "spatial_name"]], on="spatial_id", how="left"
            )
    else:
        name_column = "name" if "name" in master.columns else "spatial_name"
        master = master.merge(
            crosswalk[["spatial_id", "spatial_name", "name"]],
            left_on=name_column,
            right_on="name",
            how="inner",
        )
    return master


def _chronic_exposures(cfg: dict, crosswalk: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    master = _normalise_master(crosswalk)
    keep = ["spatial_id", "spatial_name", "nse_index"]
    comparison = list(cfg["neuro_hospitalizations"]["comparison"]["exposures"])
    exploratory = [column for column in comparison if column != "pm25_pop_weighted"]
    available = [column for column in exploratory if column in master.columns]
    for optional in ["health_n_primary_care"]:
        if optional in master.columns:
            keep.append(optional)
    exposures = master[list(dict.fromkeys([*keep, *available]))].copy()

    historical_path = REPO_ROOT / "data/processed/santiago_pm25_acag_2000_2017.csv"
    historical = pd.read_csv(historical_path)[["name", "pm25_pop_weighted"]].rename(
        columns={"pm25_pop_weighted": "pm25_hist"}
    )
    historical = historical.merge(
        crosswalk[["spatial_id", "spatial_name", "name"]], on="name", how="inner"
    )
    exposures = exposures.merge(
        historical[["spatial_id", "pm25_hist"]], on="spatial_id", how="left"
    )
    return exposures, ["pm25_hist", *available]


def _wide_annual_series(
    path: Path,
    prefix: str,
    output_name: str,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["spatial_id", "spatial_name", "year", output_name])
    wide = pd.read_csv(path)
    name_column = "name" if "name" in wide.columns else "spatial_name"
    value_columns = [column for column in wide.columns if column.startswith(f"{prefix}_")]
    long = wide.melt(
        id_vars=[name_column], value_vars=value_columns, var_name="metric_year", value_name=output_name
    )
    long["year"] = pd.to_numeric(long["metric_year"].str.extract(r"(\d{4})$")[0])
    long = long[long["year"].notna()].copy()
    long["year"] = long["year"].astype(int)
    long = long.merge(
        crosswalk[["spatial_id", "spatial_name", "name"]],
        left_on=name_column,
        right_on="name",
        how="inner",
    )
    return long[["spatial_id", "spatial_name", "year", output_name]]


def _annual_exposures(crosswalk: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    heat = _wide_annual_series(
        REPO_ROOT / "data/processed/santiago_climate_heat_by_year.csv",
        "hot_days_30c",
        "heat_hot_days_30c",
        crosswalk,
    )
    precipitation = _wide_annual_series(
        REPO_ROOT / "data/processed/santiago_precipitation_by_year.csv",
        "precip_cdd_days",
        "precip_cdd_days",
        crosswalk,
    )

    wildfire_path = REPO_ROOT / "cache/santiago_wildfire_annual_2015_2024.csv"
    wildfire = pd.read_csv(wildfire_path)
    wildfire = wildfire.merge(
        crosswalk[["spatial_id", "spatial_name", "name"]], on="name", how="inner"
    )
    area = master[["spatial_id", "area_km2"]].copy()
    wildfire = wildfire.merge(area, on="spatial_id", how="left", validate="many_to_one")
    wildfire["fire_burned_pct"] = wildfire["burned_km2"] / wildfire["area_km2"] * 100
    wildfire = wildfire[["spatial_id", "spatial_name", "year", "fire_burned_pct"]]

    annual = precipitation.merge(
        wildfire, on=["spatial_id", "spatial_name", "year"], how="outer"
    )
    annual = annual.merge(heat, on=["spatial_id", "spatial_name", "year"], how="outer")
    return annual.sort_values(["spatial_id", "year"]).reset_index(drop=True)


def _plot_trends(annual: pd.DataFrame, output_path: Path) -> None:
    outcomes = [
        "all_cause",
        *CARDIORESPIRATORY_PRIMARY,
        *NEUROPSYCHIATRIC_PRIMARY,
    ]
    regional = (
        annual[annual["outcome"].isin(outcomes)]
        .groupby(["year", "outcome"])["observed"]
        .sum()
        .reset_index()
    )
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True)
    for axis, outcome in zip(axes.flat, outcomes):
        subset = regional[regional["outcome"] == outcome]
        axis.plot(subset["year"], subset["observed"], marker="o", color="#28666E")
        axis.axvline(2020, color="#C44536", linestyle="--", alpha=0.8)
        axis.set_title(outcome.replace("_", " "))
        axis.grid(alpha=0.2)
    fig.suptitle("DEIS hospital discharges, Región Metropolitana")
    fig.supxlabel("Año de egreso")
    fig.supylabel("Egresos")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_forest(results: pd.DataFrame, output_path: Path) -> None:
    primary = results[
        (results["exposure"] == "pm25_hist") & (results["status"] == "ok")
    ].copy()
    if primary.empty:
        return
    primary = primary.sort_values(["arm", "outcome"]).reset_index(drop=True)
    y = np.arange(len(primary))
    fig, axis = plt.subplots(figsize=(8, 4.8))
    errors = np.vstack(
        [primary["rr_per_sd"] - primary["ci_low"], primary["ci_high"] - primary["rr_per_sd"]]
    )
    colors = primary["arm"].map(
        {"cardiorespiratory": "#C44536", "neuropsychiatric": "#28666E"}
    )
    for index, color in enumerate(colors):
        axis.errorbar(
            primary.loc[index, "rr_per_sd"],
            y[index],
            xerr=errors[:, index].reshape(2, 1),
            fmt="none",
            ecolor=color,
            capsize=4,
        )
    axis.scatter(primary["rr_per_sd"], y, c=colors, s=45, zorder=3)
    axis.axvline(1.0, color="black", linewidth=1, linestyle="--")
    axis.set_yticks(y, primary["outcome"].str.replace("_", " "))
    axis.set_xlabel("Razón de tasas por +1 DE de PM2.5 histórico (IC 95%)")
    axis.set_title("Egresos 2018–2019 · NB con offset observado/esperado")
    axis.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_manifest(output_dir: Path, files: list[Path], metadata: dict) -> None:
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "layer_id": "neuro_hospitalizations",
        "role": "external_health_outcome_analytics",
        "metadata": metadata,
        "files": [
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "size_bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
            }
            for path in files
            if path.exists()
        ],
    }
    write_json(output_dir / "manifest.json", manifest)


@app.command()
def run(
    city: str = typer.Option("santiago", help="Legacy city config id"),
    chunksize: int = typer.Option(250_000, min=10_000, help="Rows read per streaming block"),
) -> None:
    cfg = exposome_config.load_config(city)
    hosp_cfg = cfg["neuro_hospitalizations"]
    source_paths = [REPO_ROOT / path for path in resolve_source_paths(cfg)]
    crosswalk = _crosswalk()

    output_dir = (
        REPO_ROOT / "data/processed/cl/santiago/santiago_communes/neuro_hospitalizations"
    )
    analysis_dir = REPO_ROOT / "data/processed/cl/santiago/santiago_communes/analysis/hospitalizations"
    figures_dir = REPO_ROOT / "figures/analysis/hospitalizations"
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    inventory = archive_inventory(source_paths)
    write_json(output_dir / "source_inventory.json", {"archives": inventory})
    cube_counts, qc = aggregate_hospitalization_stream(
        source_paths,
        hosp_cfg["source"],
        crosswalk,
        hosp_cfg["years"],
        region_code=int(hosp_cfg.get("region_code", 13)),
        chunksize=chunksize,
    )

    population_path = REPO_ROOT / hosp_cfg["population"]["path"]
    population = load_ine_population_person_years(
        population_path,
        crosswalk,
        hosp_cfg["years"],
        region_code=int(hosp_cfg.get("region_code", 13)),
    )
    cube = complete_cube_with_population(cube_counts, population)
    cube_path = output_dir / "santiago_neuro_hospitalizations_2011_2020_cube.csv.gz"
    cube.to_csv(cube_path, index=False, compression="gzip")
    write_json(output_dir / "santiago_neuro_hospitalizations_2011_2020_qc.json", qc)

    windows = {
        "primary_pre_covid_2018_2019": hosp_cfg["analysis"]["primary_years"],
        "covid_sensitivity_2018_2020": hosp_cfg["analysis"]["covid_sensitivity_years"],
        "trend_pre_covid_2011_2019": hosp_cfg["analysis"]["trend_years"],
        "full_ingestion_2011_2020": hosp_cfg["years"],
    }
    window_frames = [compute_window_smr(cube, years, label) for label, years in windows.items()]
    all_windows = pd.concat(window_frames, ignore_index=True)
    windows_path = output_dir / "santiago_neuro_hospitalizations_2011_2020_windows.csv"
    all_windows.to_csv(windows_path, index=False)

    primary_smr = all_windows[all_windows["window"] == "primary_pre_covid_2018_2019"]
    exposures, exposure_columns = _chronic_exposures(cfg, crosswalk)
    exposures_path = analysis_dir / "chronic_exposure_matrix.csv"
    exposures.to_csv(exposures_path, index=False)
    chronic, residuals = fit_chronic_associations(
        primary_smr, exposures, exposure_columns, covariates=["nse_index"]
    )
    chronic_path = analysis_dir / "chronic_associations_2018_2019.csv"
    chronic.to_csv(chronic_path, index=False)

    chronic_health_path = analysis_dir / "chronic_associations_health_adjusted_2018_2019.csv"
    if "health_n_primary_care" in exposures.columns:
        chronic_health, _ = fit_chronic_associations(
            primary_smr,
            exposures,
            exposure_columns,
            covariates=["nse_index", "health_n_primary_care"],
        )
        chronic_health.to_csv(chronic_health_path, index=False)

    geometry_candidates = [
        REPO_ROOT / "data/processed/cl/santiago/santiago_communes/master.geojson",
        REPO_ROOT / "data/processed/santiago_exposome_master.geojson",
    ]
    geometry_path = next(path for path in geometry_candidates if path.exists())
    moran = residual_morans_i(residuals, geometry_path, exposure="pm25_hist")
    moran_path = analysis_dir / "chronic_pm25_residual_morans_i.csv"
    moran.to_csv(moran_path, index=False)

    annual_outcomes = compute_annual_expected(cube, hosp_cfg["years"])
    annual_outcomes_path = output_dir / "santiago_neuro_hospitalizations_annual_expected.csv.gz"
    annual_outcomes.to_csv(annual_outcomes_path, index=False, compression="gzip")
    master = _normalise_master(crosswalk)
    annual_exposures = _annual_exposures(crosswalk, master)
    annual_exposures_path = analysis_dir / "annual_exposure_matrix_2015_2020.csv"
    annual_exposures.to_csv(annual_exposures_path, index=False)
    panel_columns = ["heat_hot_days_30c", "precip_cdd_days", "fire_burned_pct"]
    panel = fit_panel_ppml(
        annual_outcomes,
        annual_exposures,
        panel_columns,
        hosp_cfg["analysis"]["panel_years"],
        window_label="panel_pre_covid_2015_2019",
    )
    panel_covid = fit_panel_ppml(
        annual_outcomes,
        annual_exposures,
        panel_columns,
        hosp_cfg["analysis"]["panel_covid_years"],
        window_label="panel_covid_sensitivity_2015_2020",
    )
    panel_all = pd.concat([panel, panel_covid], ignore_index=True)
    panel_path = analysis_dir / "annual_panel_associations_2015_2020.csv"
    panel_all.to_csv(panel_path, index=False)

    trend_figure = figures_dir / "hospitalization_trends_2011_2020.png"
    forest_figure = figures_dir / "chronic_pm25_forest_2018_2019.png"
    _plot_trends(annual_outcomes, trend_figure)
    _plot_forest(chronic, forest_figure)

    metadata = {
        "source": "DEIS open hospital-discharge data",
        "source_url": "https://deis.minsal.cl/#datosabiertos",
        "population": "INE base-2017 commune population estimates/projections",
        "population_sha256": _sha256(population_path),
        "years_ingested": list(hosp_cfg["years"]),
        "analysis_windows": windows,
        "n_communes": int(cube["spatial_id"].nunique()),
        "outcomes": list(ALL_OUTCOMES),
        "primary_outcome_families": {
            "cardiorespiratory": list(CARDIORESPIRATORY_PRIMARY),
            "neuropsychiatric": list(NEUROPSYCHIATRIC_PRIMARY),
        },
        "interpretation": "Ecological, hypothesis-generating; discharge episodes are not unique people.",
        "covid_policy": "2018-2019 primary; 2020 only in explicitly labelled sensitivity outputs.",
    }
    metadata_path = output_dir / "santiago_neuro_hospitalizations_2011_2020_metadata.json"
    write_json(metadata_path, metadata)
    _write_manifest(
        output_dir,
        [
            cube_path,
            windows_path,
            annual_outcomes_path,
            metadata_path,
            chronic_path,
            chronic_health_path,
            moran_path,
            annual_exposures_path,
            panel_path,
            trend_figure,
            forest_figure,
        ],
        metadata,
    )

    typer.echo(f"Wrote hospitalization cube: {cube_path.relative_to(REPO_ROOT)}")
    typer.echo(f"Wrote chronic associations: {chronic_path.relative_to(REPO_ROOT)}")
    typer.echo(f"Wrote annual panel: {panel_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    app()
