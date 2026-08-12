"""Compose the frozen v2.0 and v2.1 extension into a publication package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from exposome.hospitalization_annual_v2 import resolve_repo_path
from exposome.paper_plot_style import apply_astro_paper_style, save_paper_figure


BASELINE_FINGERPRINT = (
    "452459e12737f8c4ce135155c0551707e53d1701ae6c31ecef9cd1fd7f28bc38"
)
PRIMARY_EXPOSURES = frozenset(
    {
        "pm25",
        "alan",
        "heat",
        "green",
        "precipitation",
        "wind",
        "wildfire",
        "heavy_metals",
        "environmental_burden",
    }
)


def _present(value: Any) -> bool:
    return value is not None and not pd.isna(value)


def _is_true(value: Any) -> bool:
    return _present(value) and bool(value)


def bayesian_supported(row: Mapping[str, Any], minimum_probability: float) -> bool:
    if not _is_true(row.get("diagnostics_passed")):
        return False
    probability = row.get("probability_within_direction")
    low = row.get("rr_within_hdi_low")
    high = row.get("rr_within_hdi_high")
    return bool(
        _present(probability)
        and float(probability) >= minimum_probability
        and _present(low)
        and _present(high)
        and (float(low) > 1.0 or float(high) < 1.0)
    )


def practical_relevance(
    probability_in_rope: Any,
    *,
    relevant_max: float = 0.05,
    negligible_min: float = 0.95,
) -> str:
    if not _present(probability_in_rope):
        return "not_available"
    probability = float(probability_in_rope)
    if probability <= relevant_max:
        return "practically_relevant"
    if probability >= negligible_min:
        return "practically_negligible"
    return "magnitude_uncertain"


def statistical_evidence(
    row: Mapping[str, Any],
    *,
    alpha: float = 0.05,
    minimum_probability: float = 0.975,
    primary_exposures: frozenset[str] = PRIMARY_EXPOSURES,
) -> str:
    if str(row.get("status")) == "not_estimable":
        return "not_estimable"
    exposure = str(row.get("exposure"))
    core_primary = (
        exposure in primary_exposures
        and str(row.get("window")) == "primary"
        and str(row.get("outcome_family")) == "primary"
    )
    moran = row.get("residual_moran_p")
    loo_sign = row.get("loo_sign_stable")
    loo_high = row.get("loo_pareto_k_high_count")
    loo_done = row.get("loo_exact_reloo_completed")
    bayes_expected = core_primary
    unstable = (
        loo_sign is False
        or (_present(moran) and float(moran) < alpha)
        or (
            _present(loo_high)
            and _present(loo_done)
            and float(loo_done) < float(loo_high)
        )
        or (bayes_expected and not _is_true(row.get("diagnostics_passed")))
        or (core_primary and row.get("negative_control_status") != "clear")
    )
    if unstable:
        return "unstable"
    q_value = row.get("ppml_q_value")
    frequentist = _present(q_value) and float(q_value) < alpha
    bayesian = bayesian_supported(row, minimum_probability)
    if core_primary and frequentist and bayesian:
        return "supported"
    if frequentist or bayesian:
        return "suggestive"
    return "null"


def _bayesian_control_clear(row: Mapping[str, Any], minimum_probability: float) -> Any:
    explicit = row.get("bayesian_negative_control_clear")
    if _present(explicit):
        return bool(explicit)
    if not _is_true(row.get("diagnostics_passed")):
        return pd.NA
    return not bayesian_supported(row, minimum_probability)


def build_negative_control_table(
    baseline: pd.DataFrame,
    extension: pd.DataFrame,
    *,
    alpha: float,
    minimum_probability: float,
) -> pd.DataFrame:
    control_rows = baseline[
        baseline["outcome"].eq("injury_poisoning")
        & baseline["window"].eq("primary")
    ].copy()
    ppml_columns = [
        "exposure",
        "timing",
        "status",
        "ppml_rr_within",
        "ppml_rr_ci_low",
        "ppml_rr_ci_high",
        "ppml_q_value",
    ]
    ppml = control_rows[ppml_columns].rename(columns={"status": "ppml_status"})
    burden = control_rows[
        control_rows["exposure"].eq("environmental_burden")
    ].copy()
    bayes_columns = [
        "exposure",
        "timing",
        "bayesian_status",
        "diagnostics_passed",
        "rr_within",
        "rr_within_hdi_low",
        "rr_within_hdi_high",
        "probability_within_direction",
        "probability_within_in_rope",
    ]
    burden = burden[bayes_columns]
    extension_bayes = extension.rename(
        columns={"status": "bayesian_status"}
    )
    wanted_extension = [
        *bayes_columns,
        "bayesian_negative_control_clear",
        "model_id",
        "trace_sha256",
    ]
    extension_bayes = extension_bayes[
        [column for column in wanted_extension if column in extension_bayes]
    ]
    bayes = pd.concat([burden, extension_bayes], ignore_index=True, sort=False)
    table = ppml.merge(bayes, on=["exposure", "timing"], how="inner", validate="one_to_one")
    table["negative_control_ppml_clear"] = (
        table["ppml_status"].eq("ok")
        & table["ppml_q_value"].notna()
        & table["ppml_q_value"].ge(alpha)
    )
    table["negative_control_bayesian_clear"] = [
        _bayesian_control_clear(row, minimum_probability)
        for row in table.to_dict(orient="records")
    ]
    table["negative_control_status"] = [
        (
            "unstable"
            if pd.isna(bayes_clear)
            else (
                "clear"
                if bool(ppml_clear) and bool(bayes_clear)
                else "failed"
            )
        )
        for ppml_clear, bayes_clear in zip(
            table["negative_control_ppml_clear"],
            table["negative_control_bayesian_clear"],
            strict=True,
        )
    ]
    return table.sort_values(["timing", "exposure"]).reset_index(drop=True)


def compose_evidence(
    baseline: pd.DataFrame,
    controls: pd.DataFrame,
    *,
    alpha: float = 0.05,
    minimum_probability: float = 0.975,
) -> pd.DataFrame:
    mapping = controls[
        [
            "exposure",
            "timing",
            "negative_control_ppml_clear",
            "negative_control_bayesian_clear",
            "negative_control_status",
        ]
    ]
    evidence = baseline.drop(
        columns=["negative_control_clear", "evidence_label"], errors="ignore"
    ).merge(mapping, on=["exposure", "timing"], how="left", validate="many_to_one")
    evidence = evidence.copy()
    evidence["statistical_evidence"] = [
        statistical_evidence(
            row,
            alpha=alpha,
            minimum_probability=minimum_probability,
        )
        for row in evidence.to_dict(orient="records")
    ]
    evidence["practical_relevance"] = [
        practical_relevance(value)
        for value in evidence.get(
            "probability_within_in_rope", pd.Series(pd.NA, index=evidence.index)
        )
    ]
    return evidence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _forest_plot(table: pd.DataFrame, output: Path) -> list[Path]:
    primary = table[
        table["outcome_family"].eq("primary")
        & table["window"].eq("primary")
        & table["exposure"].isin(PRIMARY_EXPOSURES)
        & table["rr_within"].notna()
    ].copy()
    priority = {"supported": 0, "suggestive": 1, "unstable": 2, "null": 3}
    primary["priority"] = primary["statistical_evidence"].map(priority).fillna(4)
    primary = primary.sort_values(["priority", "ppml_q_value"]).head(24)
    primary["label"] = (
        primary["exposure"].astype(str)
        + " · "
        + primary["outcome"].astype(str)
        + " · "
        + primary["timing"].astype(str)
    )
    fig, ax = plt.subplots(figsize=(7.0, max(4.5, 0.25 * len(primary))))
    y = np.arange(len(primary))
    ax.axvspan(0.95, 1.05, color="#D9D9D9", alpha=0.6, label="ROPE 0.95–1.05")
    ax.axvline(1.0, color="black", linewidth=1.0)
    colors = primary["statistical_evidence"].map(
        {"supported": "#0072B2", "suggestive": "#E69F00", "unstable": "#CC79A7", "null": "#777777"}
    )
    ax.errorbar(
        primary["rr_within"],
        y,
        xerr=np.vstack(
            [
                primary["rr_within"] - primary["rr_within_hdi_low"],
                primary["rr_within_hdi_high"] - primary["rr_within"],
            ]
        ),
        fmt="none",
        ecolor="0.4",
        elinewidth=1.2,
        capsize=2,
    )
    ax.scatter(primary["rr_within"], y, c=colors, s=24, zorder=3)
    ax.set_yticks(y, primary["label"])
    ax.invert_yaxis()
    ax.set_xlabel("Rate ratio per within-commune SD (95% HDI)")
    ax.set_title("Primary annual associations")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", color="#0072B2", label="supported"),
            Line2D([], [], marker="o", linestyle="none", color="#E69F00", label="suggestive"),
            Line2D([], [], marker="o", linestyle="none", color="#CC79A7", label="unstable"),
        ],
        loc="lower right",
    )
    return save_paper_figure(fig, output / "figures/figure_2_primary_forest")


def _coverage_plot(outcomes: pd.DataFrame, output: Path) -> list[Path]:
    totals = outcomes.groupby(["year", "outcome"], as_index=False)["observed"].sum()
    selected = totals[totals["outcome"].isin(["cardiovascular", "respiratory", "respiratory_copd", "cerebrovascular", "mental_all"])]
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for outcome, group in selected.groupby("outcome"):
        ax.plot(group["year"], group["observed"], marker="o", linewidth=1.4, label=outcome)
    ax.axvspan(2015, 2019, color="#56B4E9", alpha=0.12, label="primary window")
    ax.axvline(2020, color="#D55E00", linestyle="--", linewidth=1.0, label="COVID sensitivity")
    ax.set_xlabel("Year")
    ax.set_ylabel("Observed admissions")
    ax.set_title("Outcome coverage and temporal window")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    return save_paper_figure(fig, output / "figures/figure_1_data_coverage")


def _negative_control_plot(controls: pd.DataFrame, output: Path) -> list[Path]:
    table = controls.copy()
    table["label"] = table["exposure"] + " · " + table["timing"]
    fig, ax = plt.subplots(figsize=(7.0, 5.2))
    y = np.arange(len(table))
    ax.axvspan(0.95, 1.05, color="#D9D9D9", alpha=0.6)
    ax.axvline(1.0, color="black", linewidth=1.0)
    color = table["negative_control_status"].map(
        {"clear": "#009E73", "failed": "#D55E00", "unstable": "#CC79A7"}
    )
    ax.errorbar(
        table["rr_within"],
        y,
        xerr=np.vstack(
            [
                table["rr_within"] - table["rr_within_hdi_low"],
                table["rr_within_hdi_high"] - table["rr_within"],
            ]
        ),
        fmt="none",
        ecolor="0.4",
        elinewidth=1.2,
        capsize=2,
    )
    ax.scatter(table["rr_within"], y, c=color, s=24, zorder=3)
    ax.set_yticks(y, table["label"])
    ax.invert_yaxis()
    ax.set_xlabel("Negative-control rate ratio (95% HDI)")
    ax.set_title("Bayesian negative-control results")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", color="#009E73", label="combined gate clear"),
            Line2D([], [], marker="o", linestyle="none", color="#D55E00", label="combined gate failed"),
        ],
        loc="lower right",
    )
    return save_paper_figure(fig, output / "figures/figure_3_negative_controls")


def _timing_plot(table: pd.DataFrame, output: Path) -> list[Path]:
    wind = table[
        table["exposure"].eq("wind")
        & table["outcome_family"].eq("primary")
        & table["window"].eq("primary")
        & table["rr_within"].notna()
    ].copy()
    outcomes = list(dict.fromkeys(wind["outcome"].tolist()))
    x = np.arange(len(outcomes))
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for offset, timing, color in [(-0.12, "same_year", "#E69F00"), (0.12, "lag1", "#0072B2")]:
        group = wind[wind["timing"].eq(timing)].set_index("outcome").reindex(outcomes)
        ax.errorbar(
            x + offset,
            group["rr_within"],
            yerr=np.vstack(
                [
                    group["rr_within"] - group["rr_within_hdi_low"],
                    group["rr_within_hdi_high"] - group["rr_within"],
                ]
            ),
            fmt="o",
            color=color,
            capsize=3,
            label=timing,
        )
    ax.axhspan(0.95, 1.05, color="#D9D9D9", alpha=0.5)
    ax.axhline(1.0, color="black", linewidth=1.0)
    ax.set_xticks(x, outcomes, rotation=25, ha="right")
    ax.set_ylabel("Rate ratio per within-commune SD")
    ax.set_title("Wind estimates by temporal alignment")
    ax.legend()
    ax.grid(axis="y", color="0.88", linewidth=0.6)
    return save_paper_figure(fig, output / "figures/figure_4_timing_sensitivity")


def _joint_plot(joint_path: Path, output: Path) -> list[Path]:
    table = pd.read_csv(joint_path)
    frequency = (
        table.groupby("term")["selection_frequency"]
        .mean()
        .sort_values(ascending=True)
    )
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.barh(frequency.index, frequency.values, color="#56B4E9")
    ax.axvline(0.8, color="#D55E00", linestyle="--", linewidth=1.0)
    ax.set_xlabel("Mean bootstrap selection frequency")
    ax.set_title("Joint elastic-net stability")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    return save_paper_figure(fig, output / "figures/figure_5_joint_selection")


def build_publication_package(
    repo_root: Path,
    *,
    baseline_dir: Path,
    extension_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    baseline_dir = resolve_repo_path(repo_root, baseline_dir)
    extension_dir = resolve_repo_path(repo_root, extension_dir)
    output_dir = resolve_repo_path(repo_root, output_dir)
    baseline_acceptance = json.loads(
        (baseline_dir / "publication_acceptance.json").read_text(encoding="utf-8")
    )
    extension_acceptance = json.loads(
        (extension_dir / "publication_acceptance.json").read_text(encoding="utf-8")
    )
    if baseline_acceptance.get("status") != "complete":
        raise ValueError("annual-v2.0 is not complete")
    if baseline_acceptance.get("scientific_fingerprint") != BASELINE_FINGERPRINT:
        raise ValueError("Unexpected annual-v2.0 fingerprint")
    if extension_acceptance.get("status") != "complete":
        raise ValueError("annual-v2.1 control extension is not complete")
    if extension_acceptance.get("baseline_fingerprint") != BASELINE_FINGERPRINT:
        raise ValueError("annual-v2.1 is not bound to the frozen baseline")

    baseline = pd.read_csv(baseline_dir / "evidence_table.csv")
    extension = pd.read_csv(extension_dir / "negative_control_evidence.csv")
    controls = build_negative_control_table(
        baseline,
        extension,
        alpha=0.05,
        minimum_probability=0.975,
    )
    evidence = compose_evidence(baseline, controls)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = output_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(tables / "table_s1_complete_evidence.csv", index=False)
    controls.to_csv(tables / "table_s2_negative_controls.csv", index=False)
    primary = evidence[
        evidence["outcome_family"].eq("primary")
        & evidence["window"].eq("primary")
        & evidence["exposure"].isin(PRIMARY_EXPOSURES)
    ].copy()
    primary.to_csv(tables / "table_1_primary_effects.csv", index=False)
    supported = primary[primary["statistical_evidence"].eq("supported")].copy()
    supported.to_csv(tables / "table_2_supported_signals.csv", index=False)

    apply_astro_paper_style(profile="compact")
    outcomes = pd.read_csv(baseline_dir / "annual_outcomes.csv")
    generated_figures: list[Path] = []
    generated_figures += _coverage_plot(outcomes, output_dir)
    generated_figures += _forest_plot(evidence, output_dir)
    generated_figures += _negative_control_plot(controls, output_dir)
    generated_figures += _timing_plot(evidence, output_dir)
    generated_figures += _joint_plot(
        baseline_dir / "joint/elastic_net_coefficients.csv", output_dir
    )
    plt.close("all")

    evidence_counts = evidence["statistical_evidence"].value_counts().to_dict()
    practical_counts = primary["practical_relevance"].value_counts().to_dict()
    failed_controls = controls[
        controls["negative_control_status"].ne("clear")
    ][["exposure", "timing"]]
    failed_control_text = ", ".join(
        f"{row.exposure} ({row.timing})"
        for row in failed_controls.itertuples(index=False)
    )
    supported_lines = [
        (
            f"- {row.exposure} ({row.timing}) and {row.outcome}: "
            f"RR {row.rr_within:.3f}, 95% HDI {row.rr_within_hdi_low:.3f}–"
            f"{row.rr_within_hdi_high:.3f}; {row.practical_relevance}."
        )
        for row in supported.itertuples(index=False)
    ] or ["- No association passed every prespecified statistical gate."]
    manuscript = "\n".join(
        [
            "# Annual urban exposome and hospital admissions across Santiago communes",
            "",
            "## Abstract",
            "",
            "We conducted an ecological longitudinal analysis of annual environmental exposures and hospital admissions across 52 communes in Metropolitan Santiago. The panel combines DEIS discharges from 2011–2020 with annual exposure products, while primary inference is restricted to the pre-COVID window and uses within-commune change. Associations were screened with commune and year fixed-effects PPML and evaluated with negative-binomial space–time BYM2 models, multiplicity control, residual spatial diagnostics, leave-one-commune-out stability, PSIS-LOO, negative controls, and a prespecified rate-ratio ROPE of 0.95–1.05. Results are separated into statistical evidence and practical relevance. The design supports ecological association and hypothesis generation, not causal or individual-level claims.",
            "",
            "## Methods",
            "",
            "The materialized outcome cube contains 52 communes, 10 years, and 16 outcome families (8,320 commune-year-outcome cells). Primary models use outcome years 2015–2019 and compare same-year with one-year-lag exposure alignment. Exposure effects are reported per standard deviation of within-commune temporal change. Statistical support requires FDR-adjusted PPML evidence, concordant BYM2 direction with a 95% HDI excluding one, stable leave-one-commune-out direction, resolved PSIS-LOO diagnostics, no residual Moran signal at alpha 0.05, and clear matched PPML and Bayesian negative controls. Practical relevance is classified independently from posterior mass inside the ROPE.",
            "",
            "## Results",
            "",
            f"The frozen v2.0 analysis completed 768 screening tasks, 10 joint models, and 142 BYM2 models. The v2.1 extension completed 16 additional exposure-specific Bayesian negative controls; together with the two original burden controls, the package evaluates 18 Bayesian controls. The combined PPML/BYM2 negative-control gate was clear for {(controls['negative_control_status'] == 'clear').sum()}/18 comparisons and failed for {(controls['negative_control_status'] != 'clear').sum()}/18: {failed_control_text}. Combined evidence counts were {json.dumps(evidence_counts, sort_keys=True)}. Primary practical-relevance counts were {json.dumps(practical_counts, sort_keys=True)}.",
            "",
            "Associations passing every statistical gate:",
            "",
            *supported_lines,
            "",
            "## Discussion",
            "",
            "Any statistically supported association should be interpreted alongside its ROPE classification. Directional posterior evidence can coexist with a small or uncertain practical magnitude. Negative-control failures, residual spatial autocorrelation, short effective temporal support, correlated meteorological exposures, ecological aggregation, and hospital-use patterns restrict interpretation. These findings motivate replication and targeted etiologic studies; they do not establish causation.",
            "",
            "## Data and code availability",
            "",
            "The repository contains the registered protocols, deterministic task registries, tests, aggregate result tables, figure-generation code, and SHA-256 manifests. Patient-level records and multi-gigabyte posterior traces are not included in the manuscript package.",
            "",
        ]
    )
    _write(output_dir / "manuscript.md", manuscript)

    supplement = "\n".join(
        [
            "# Supplementary methods and results",
            "",
            "## Prespecified gates",
            "",
            "Statistical evidence and practical relevance are independent axes. Posterior ROPE mass at or below 0.05 is labelled practically relevant, at or above 0.95 practically negligible, and otherwise magnitude uncertain. A Bayesian negative control is clear only when diagnostics pass and it lacks both posterior direction probability ≥0.975 and a 95% HDI wholly on one side of RR=1.",
            "",
            "## Model inventory",
            "",
            "v2.0 contains 142 registered BYM2 models. v2.1 adds 16 exposure-specific injury/poisoning controls without modifying or rebinding v2.0 traces. The combined scientific package therefore references 158 models under two immutable fingerprints.",
            "",
            "## Interpretation boundary",
            "",
            "All estimates are ecological rate-ratio associations. They must not be translated into individual risk or causal effects.",
            "",
        ]
    )
    _write(output_dir / "supplement.md", supplement)
    reproducibility = "\n".join(
        [
            "# Reproducibilidad operativa",
            "",
            f"- Fingerprint v2.0 congelado: `{BASELINE_FINGERPRINT}`.",
            f"- Fingerprint v2.1: `{extension_acceptance['scientific_fingerprint']}`.",
            "- v2.0: 768/768 screening, 10/10 elastic-net y 142/142 BYM2.",
            "- v2.1: 16/16 controles BYM2.",
            "- Interpretación causal: no aceptada.",
            "",
            "Comandos de verificación:",
            "",
            "```bash",
            ".venv/bin/python scripts/run_hospitalization_controls_v2_1.py --phase status",
            ".venv/bin/python scripts/build_hospitalization_publication_package.py",
            "PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest tests.test_hospitalization_annual_v2 tests.test_hospitalization_controls_v2_1 tests.test_hospitalization_publication",
            "```",
            "",
            "Las trazas se conservan fuera del paquete por tamaño; sus hashes están en los sidecars y en las tablas de control.",
            "",
        ]
    )
    _write(output_dir / "reproducibility.md", reproducibility)

    package_files = sorted(
        path for path in output_dir.rglob("*") if path.is_file() and path.name != "results_manifest.json"
    )
    source_files = [
        baseline_dir / "publication_acceptance.json",
        baseline_dir / "evidence_table.csv",
        extension_dir / "publication_acceptance.json",
        extension_dir / "negative_control_evidence.csv",
    ]
    manifest = {
        "schema_version": 1,
        "title": "Annual urban exposome and hospital admissions across Santiago communes",
        "interpretation": "ecological_association_not_causal",
        "baseline_fingerprint": BASELINE_FINGERPRINT,
        "extension_fingerprint": extension_acceptance["scientific_fingerprint"],
        "model_inventory": {"v2_0": 142, "v2_1": 16, "combined": 158},
        "negative_control_inventory": {"v2_0": 2, "v2_1": 16, "combined": 18},
        "source_sha256": {
            str(path.relative_to(repo_root)): _sha256(path) for path in source_files
        },
        "files": [
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in package_files
        ],
    }
    _write(output_dir / "results_manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest
