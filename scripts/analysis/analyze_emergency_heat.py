#!/usr/bin/env python3
"""Quality-gated pilot: acute heat and RM emergency cardiovascular demand."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from tqdm import tqdm
import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.emergency_visits import (  # noqa: E402
    add_heat_exposures,
    aggregate_emergency_zip,
    build_regional_temperature,
    build_stable_crosswalk,
    fit_negative_binomial,
    fit_poisson_hac,
    prepare_model_frame,
    retention_verdict,
)


app = typer.Typer(add_completion=False)


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _clean_json(value),
            ensure_ascii=False,
            indent=2,
            default=_json_default,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_or_scan_direct(
    raw_dir: Path,
    cache_dir: Path,
    year: int,
    force: bool,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    daily_path = cache_dir / f"emergency_visits_daily_{year}.csv"
    diagnostics_path = cache_dir / f"emergency_visits_diagnostics_{year}.json"
    crosswalk_path = cache_dir / f"emergency_visits_crosswalk_{year}.csv"
    if not force and all(path.exists() for path in [daily_path, diagnostics_path, crosswalk_path]):
        return (
            pd.read_csv(daily_path, parse_dates=["date"]),
            json.loads(diagnostics_path.read_text(encoding="utf-8")),
            pd.read_csv(crosswalk_path, dtype=str),
        )
    result = aggregate_emergency_zip(
        raw_dir / f"AtencionesUrgencia{year}.zip",
        year=year,
    )
    result.daily.to_csv(daily_path, index=False)
    result.crosswalk_records.to_csv(crosswalk_path, index=False)
    _write_json(diagnostics_path, result.diagnostics)
    return result.daily, result.diagnostics, result.crosswalk_records


def _load_or_scan_historical(
    raw_dir: Path,
    cache_dir: Path,
    year: int,
    stable_crosswalk: dict[str, str],
    force: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    daily_path = cache_dir / f"emergency_visits_daily_{year}.csv"
    diagnostics_path = cache_dir / f"emergency_visits_diagnostics_{year}.json"
    if not force and daily_path.exists() and diagnostics_path.exists():
        return (
            pd.read_csv(daily_path, parse_dates=["date"]),
            json.loads(diagnostics_path.read_text(encoding="utf-8")),
        )
    result = aggregate_emergency_zip(
        raw_dir / f"AtencionesUrgencia{year}.zip",
        year=year,
        stable_crosswalk=stable_crosswalk,
    )
    result.daily.to_csv(daily_path, index=False)
    _write_json(diagnostics_path, result.diagnostics)
    return result.daily, result.diagnostics


def _model_row(
    frame: pd.DataFrame,
    *,
    label: str,
    arm: str,
    outcome: str,
    count_column: str,
    exposure: str,
    method: str = "poisson",
) -> dict[str, Any]:
    if method == "negative_binomial":
        result = fit_negative_binomial(frame, exposure=exposure)
    else:
        result = fit_poisson_hac(frame, exposure=exposure)
    return {
        "label": label,
        "arm": arm,
        "outcome": outcome,
        "count_column": count_column,
        **result,
    }


def _plot_diagnostics(
    direct: pd.DataFrame,
    results: pd.DataFrame,
    threshold: float,
    output_path: Path,
) -> None:
    primary = direct.sort_values("date").copy()
    figure, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    axes[0, 0].plot(primary["date"], primary["temperature_2m_max"], lw=0.8, color="#d95f02")
    axes[0, 0].axhline(threshold, color="#7f0000", ls="--", lw=1.2, label="Percentil 95")
    axes[0, 0].set(title="Temperatura máxima regional", ylabel="°C")
    axes[0, 0].legend(frameon=False)

    axes[0, 1].plot(
        primary["date"],
        primary["count"].rolling(7, center=True).mean(),
        lw=1.0,
        color="#1b7837",
    )
    axes[0, 1].set(title="Urgencias circulatorias 65+ (media móvil 7 días)", ylabel="Atenciones")

    forest = results.loc[
        results["arm"].isin(["primary", "sensitivity"])
        & results["rr"].notna()
        & ~results["label"].str.contains("placebo")
    ].copy()
    forest = forest.tail(9).reset_index(drop=True)
    positions = np.arange(len(forest))
    axes[1, 0].errorbar(
        forest["rr"],
        positions,
        xerr=[forest["rr"] - forest["ci_low"], forest["ci_high"] - forest["rr"]],
        fmt="o",
        color="#2166ac",
        capsize=3,
    )
    axes[1, 0].axvline(1, color="0.35", ls="--")
    axes[1, 0].set_yticks(positions, forest["label"])
    axes[1, 0].set(title="Sensibilidades: RR por +1 °C de exceso", xlabel="Razón de tasas")

    axes[1, 1].plot(
        primary["date"], primary["reporting_establishments"], lw=0.8, color="#542788"
    )
    axes[1, 1].set(title="Establecimientos informantes — causa circulatoria", ylabel="N")
    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(alpha=0.18)
    figure.suptitle("Piloto DEIS: calor y demanda cardiovascular de urgencia — RM")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


@app.command()
def main(
    raw_dir: Path = typer.Option(REPO_ROOT / "data/raw/deis/atenciones_urgencia"),
    climate_daily: Path = typer.Option(
        REPO_ROOT / "data/processed/santiago_climate_openmeteo_daily_2015_2024.csv"
    ),
    demography: Path = typer.Option(
        REPO_ROOT
        / "data/processed/cl/santiago/santiago_communes/demography/santiago_demography.csv"
    ),
    cache_dir: Path = typer.Option(REPO_ROOT / "cache/emergency_visits"),
    output_dir: Path = typer.Option(REPO_ROOT / "data/processed/analysis"),
    figure_path: Path = typer.Option(REPO_ROOT / "figures/santiago_heat_emergency_pilot.png"),
    force: bool = typer.Option(False, help="Ignore annual aggregation caches."),
) -> None:
    """Run the local-only quality gate and write a keep/remove verdict."""

    required_years = range(2020, 2026)
    missing = [year for year in required_years if not (raw_dir / f"AtencionesUrgencia{year}.zip").exists()]
    if missing:
        raise typer.BadParameter(f"Missing DEIS ZIP years: {missing}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    annual_daily: dict[int, pd.DataFrame] = {}
    diagnostics: dict[int, dict[str, Any]] = {}
    crosswalk_parts: list[pd.DataFrame] = []
    for year in tqdm([2023, 2024, 2025], desc="Direct-geography DEIS years"):
        daily, diagnostic, records = _load_or_scan_direct(raw_dir, cache_dir, year, force)
        annual_daily[year] = daily
        diagnostics[year] = diagnostic
        crosswalk_parts.append(records)
    crosswalk_records = pd.concat(crosswalk_parts, ignore_index=True)
    stable_crosswalk, crosswalk_summary = build_stable_crosswalk(crosswalk_records)
    crosswalk_records.to_csv(cache_dir / "emergency_visits_crosswalk_records.csv", index=False)
    crosswalk_summary.to_csv(cache_dir / "emergency_visits_crosswalk_summary.csv", index=False)

    for year in tqdm([2020, 2021, 2022], desc="Historical DEIS years"):
        daily, diagnostic = _load_or_scan_historical(
            raw_dir, cache_dir, year, stable_crosswalk, force
        )
        annual_daily[year] = daily
        diagnostics[year] = diagnostic

    daily = pd.concat([annual_daily[year] for year in range(2020, 2025)], ignore_index=True)
    daily = daily.sort_values(["date", "outcome"]).reset_index(drop=True)
    daily.to_csv(output_dir / "santiago_emergency_visits_daily_2020_2024.csv", index=False)

    regional_path = output_dir / "santiago_regional_temperature_daily_2015_2024.csv"
    regional_metadata_path = (
        output_dir / "santiago_regional_temperature_daily_2015_2024_metadata.json"
    )
    if climate_daily.exists():
        regional, climate_metadata = build_regional_temperature(climate_daily, demography)
        regional.to_csv(regional_path, index=False)
    elif regional_path.exists() and regional_metadata_path.exists():
        regional = pd.read_csv(regional_path, parse_dates=["date"])
        climate_metadata = json.loads(regional_metadata_path.read_text(encoding="utf-8"))
        climate_metadata["reused_derived_exposure"] = True
    else:
        raise typer.BadParameter(
            "Missing both the commune daily climate input and the derived regional series: "
            f"{climate_daily}; {regional_path}"
        )
    exposures, thresholds = add_heat_exposures(regional)
    _write_json(
        regional_metadata_path,
        {**climate_metadata, "thresholds": thresholds},
    )

    frames: dict[str, pd.DataFrame] = {}
    frame_specs = {
        "direct_primary": ("circulatory", "count_65_plus", "2023-01-01", "2024-12-31"),
        "extended_primary": ("circulatory", "count_65_plus", "2020-01-01", "2024-12-31"),
        "post_acute_pandemic": ("circulatory", "count_65_plus", "2022-01-01", "2024-12-31"),
        "year_2023": ("circulatory", "count_65_plus", "2023-01-01", "2023-12-31"),
        "year_2024": ("circulatory", "count_65_plus", "2024-01-01", "2024-12-31"),
    }
    for name, (outcome, count_column, start, end) in frame_specs.items():
        frames[name] = prepare_model_frame(
            daily,
            exposures,
            outcome=outcome,
            count_column=count_column,
            start_date=start,
            end_date=end,
        )

    result_rows: list[dict[str, Any]] = []
    direct = frames["direct_primary"]
    result_rows.append(
        _model_row(
            direct,
            label="Primario 2023-2024",
            arm="primary",
            outcome="circulatory",
            count_column="count_65_plus",
            exposure="heat_excess_lag03",
        )
    )
    result_rows.append(
        _model_row(
            direct,
            label="Primario NB 2023-2024",
            arm="sensitivity",
            outcome="circulatory",
            count_column="count_65_plus",
            exposure="heat_excess_lag03",
            method="negative_binomial",
        )
    )
    for frame_name, label in [
        ("extended_primary", "Extensión 2020-2024"),
        ("post_acute_pandemic", "Sensibilidad 2022-2024"),
        ("year_2023", "Solo 2023"),
        ("year_2024", "Solo 2024"),
    ]:
        result_rows.append(
            _model_row(
                frames[frame_name],
                label=label,
                arm="sensitivity",
                outcome="circulatory",
                count_column="count_65_plus",
                exposure="heat_excess_lag03",
            )
        )
    for exposure, label in [
        ("heat_excess", "Lag 0"),
        ("apparent_heat_excess_lag03", "Temperatura aparente lag 0-3"),
        ("placebo_heat_excess_lead7", "Placebo temperatura futura +7"),
    ]:
        result_rows.append(
            _model_row(
                direct,
                label=label,
                arm="placebo" if "placebo" in label.lower() else "sensitivity",
                outcome="circulatory",
                count_column="count_65_plus",
                exposure=exposure,
            )
        )

    secondary_specs = [
        ("circulatory", "count_total", "Circulatorias todas las edades"),
        ("ami", "count_total", "Infarto todas las edades"),
        ("ami", "count_65_plus", "Infarto 65+"),
        ("stroke", "count_total", "ACV todas las edades"),
        ("stroke", "count_65_plus", "ACV 65+"),
    ]
    for outcome, count_column, label in secondary_specs:
        frame = prepare_model_frame(
            daily,
            exposures,
            outcome=outcome,
            count_column=count_column,
            start_date="2023-01-01",
            end_date="2024-12-31",
        )
        result_rows.append(
            _model_row(
                frame,
                label=label,
                arm="secondary",
                outcome=outcome,
                count_column=count_column,
                exposure="heat_excess_lag03",
            )
        )
    for outcome, label in [
        ("respiratory", "Respiratorias exploratorias"),
        ("mental", "Salud mental exploratoria"),
        ("self_harm", "Autolesiones exploratorias"),
    ]:
        frame = prepare_model_frame(
            daily,
            exposures,
            outcome=outcome,
            count_column="count_total",
            start_date="2023-01-01",
            end_date="2024-12-31",
        )
        result_rows.append(
            _model_row(
                frame,
                label=label,
                arm="exploratory",
                outcome=outcome,
                count_column="count_total",
                exposure="heat_excess_lag03",
            )
        )

    results = pd.DataFrame(result_rows)
    results["q_bh"] = np.nan
    for arm in ["secondary", "exploratory"]:
        mask = results["arm"].eq(arm)
        if mask.any():
            results.loc[mask, "q_bh"] = multipletests(results.loc[mask, "p_value"], method="fdr_bh")[1]
    results.to_csv(output_dir / "santiago_heat_emergency_results.csv", index=False)

    primary_result = results.loc[results["label"].eq("Primario 2023-2024")].iloc[0].to_dict()
    nb_result = results.loc[results["label"].eq("Primario NB 2023-2024")].iloc[0].to_dict()
    placebo_result = results.loc[
        results["label"].eq("Placebo temperatura futura +7")
    ].iloc[0].to_dict()
    direct_gate_frame = direct.dropna(subset=["heat_excess_lag03"])
    verdict = retention_verdict(
        direct_frame=direct_gate_frame,
        primary_result=primary_result,
        nb_result=nb_result,
        placebo_result=placebo_result,
        yearly_diagnostics=diagnostics.values(),
        expected_direct_days=731,
    )
    summary = {
        "analysis": "acute heat and RM emergency cardiovascular demand",
        "primary_outcome": "circulatory emergency visits, age 65+",
        "primary_window": "2023-2024",
        "inference_unit": "daily demand at reporting establishments in Region Metropolitana",
        "thresholds": thresholds,
        "yearly_diagnostics": [diagnostics[year] for year in sorted(diagnostics)],
        "crosswalk": {
            "establishments_observed": len(crosswalk_summary),
            "stable_establishments": int(crosswalk_summary["stable"].sum()),
            "conflicting_establishments": int((~crosswalk_summary["stable"]).sum()),
        },
        "primary_result": primary_result,
        "negative_binomial_sensitivity": nb_result,
        "placebo_result": placebo_result,
        "retention_gate": verdict,
        "limitations": [
            "Establishment location is not patient residence.",
            "The primary direct-geography window covers only 2023-2024.",
            "No daily air-pollution adjustment is available in this pilot.",
            "2025 is excluded because matched daily temperature ends in 2024.",
        ],
    }
    _write_json(output_dir / "santiago_heat_emergency_summary.json", summary)
    _plot_diagnostics(direct_gate_frame, results, thresholds["temperature_2m_max"], figure_path)

    typer.echo(results.round(4).to_string(index=False))
    typer.echo(f"\nRetention verdict: {verdict['verdict']}")
    if verdict["direct_gate_reasons"]:
        typer.echo(f"Direct gate reasons: {verdict['direct_gate_reasons']}")
    if verdict["crosswalk_gate_reasons"]:
        typer.echo(f"Crosswalk gate reasons: {verdict['crosswalk_gate_reasons']}")


if __name__ == "__main__":
    app()
