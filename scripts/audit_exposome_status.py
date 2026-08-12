from __future__ import annotations

import argparse
import ast
import csv
import difflib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
DOCS_DIR = ROOT / "docs"
DEFAULT_STUDY = "santiago_communes"
STATUS_CSV = DOCS_DIR / "exposome_status.csv"
STATUS_MD = DOCS_DIR / "exposome_status.md"
PROMPTS_DIR = DOCS_DIR / "review_prompts"
EXPECTED_COMMUNES = 52

MANUAL_FIELDS = [
    "review_status",
    "review_tool",
    "review_date",
    "review_doc",
    "blockers",
    "next_action",
    "final_check",
]

CSV_FIELDS = [
    "layer_id",
    "factor",
    "category",
    "required_or_optional",
    "run_command",
    "csv_path",
    "geojson_path",
    "metadata_path",
    "methodology_doc",
    "figure_or_map",
    "rows",
    "expected_rows",
    "unique_names",
    "duplicate_names",
    "missing_names",
    "required_columns_ok",
    "missing_required_columns",
    "in_master",
    "auto_status",
    *MANUAL_FIELDS,
]


FACTOR_LABELS = {
    "socioeconomic": "Nivel socioeconomico",
    "air_quality": "Calidad del aire legacy",
    "air_quality_pm25": "PM2.5 cronico",
    "heavy_metals": "Metales pesados industriales",
    "air_quality_satellite": "Calidad del aire satelital",
    "alan": "Luz artificial nocturna",
    "sleep_context": "Contexto sueno-circadiano",
    "greenspace_access": "Areas verdes - acceso",
    "greenspace_coverage": "Areas verdes - cobertura satelital",
    "greenspace_multisource": "Areas verdes - integración multifuente",
    "healthcare": "Acceso a salud",
    "demography": "Demografia",
    "climate_heat": "Clima y calor urbano",
    "precipitation": "Precipitacion CHIRPS",
    "precipitation_spi": "Sequias SPI",
    "climate_openmeteo": "Metricas climaticas anuales",
    "wildfire": "Incendios forestales",
    "noise": "Ruido urbano",
    "noise_spain": "Ruido MER/SICA España",
    "walkability": "Caminabilidad",
    "public_transport": "Transporte publico",
    "social_infrastructure": "Infraestructura social",
    "food_environment": "Entorno alimentario",
    "greenspace_cv": "Validacion CV de vegetacion",
    "neuro_mortality": "Comparador mortalidad neurologica",
    "neuro_hospitalizations": "Comparador egresos neuropsiquiatricos",
    "pobreza_sae": "Pobreza comunal SAE",
}

METHODOLOGY_DOCS = {
    "socioeconomic": "docs/socioeconomic_methodology.md",
    "air_quality": "docs/air_quality_legacy_methodology.md",
    "air_quality_satellite": "docs/plan_a_plus_methodology.md",
    "air_quality_pm25": "docs/pm25_methodology.md",
    "pm25": "docs/pm25_methodology.md",
    "alan": "docs/alan_methodology.md",
    "climate_heat": "docs/climate_heat_methodology.md",
    "climate_openmeteo": "docs/climate_openmeteo_methodology.md",
    "precipitation": "docs/precipitation_methodology.md",
    "wildfire": "docs/wildfire_methodology.md",
    "demography": "docs/demography_methodology.md",
    "greenspace_access": "docs/greenspace_access_methodology.md",
    "greenspace_coverage": "docs/greenspace_coverage_methodology.md",
    "greenspace_multisource": "docs/greenspace_multisource_methodology.md",
    "greenspace_cv": "docs/greenspace_cv_methodology.md",
    "healthcare": "docs/healthcare_methodology.md",
    "heavy_metals": "docs/heavy_metals_methodology.md",
    "sleep_context": "docs/sleep_context_methodology.md",
    "social_infrastructure": "docs/social_infrastructure_methodology.md",
    "food_environment": "docs/food_environment_methodology.md",
    "food_insecurity": "docs/food_insecurity_methodology.md",
    "wind": "docs/wind_methodology.md",
    "noise": "docs/noise_methodology.md",
    "noise_spain": "docs/noise_spain_methodology.md",
    "walkability": "docs/walkability_methodology.md",
    "public_transport": "docs/public_transport_methodology.md",
    "neuro_mortality": "docs/neuro_outcomes_methodology.md",
    "neuro_hospitalizations": "docs/neuro_outcomes_methodology.md",
    "pobreza_sae": "docs/pobreza_sae_methodology.md",
}

FIGURES = {
    "socioeconomic": "figures/socioeconomic_santiago_4panel.png",
    "air_quality": "figures/air_quality_before_after_satellite.png",
    "air_quality_satellite": "figures/air_quality_satellite_santiago_4panel.png",
    "air_quality_pm25": "figures/pm25_santiago_4panel.png",
    "heavy_metals": "figures/heavy_metals_santiago_4panel.png",
    "alan": "figures/alan_santiago_4panel.png",
    "sleep_context": "figures/sleep_context_santiago.png",
    "greenspace_access": "figures/greenspace_access_santiago_2panel.png",
    "greenspace_coverage": "figures/greenspace_coverage_santiago_2panel.png",
    "greenspace_cv": "figures/greenspace_cv_santiago.png",
    "healthcare": "figures/healthcare_access_santiago.png",
    "climate_heat": "figures/climate_heat_santiago_pub.png",
    "wildfire": "figures/wildfire_santiago_4panel.png",
    "precipitation": "figures/precipitation_santiago_4panel.png",
    "precipitation_spi": "figures/precipitation_spi_santiago_4panel.png",
    "climate_openmeteo": "figures/climate_metrics_santiago.png",
    "demography": "figures/demography_santiago_2panel.png",
    "noise": "figures/noise_santiago_4panel.png",
    "walkability": "figures/walkability_santiago_4panel.png",
    "public_transport": "figures/public_transport_santiago_4panel.png",
    "neuro_mortality": "figures/neuro_outcomes_santiago_4panel.png",
    "neuro_hospitalizations": "figures/neuro_outcomes_santiago_4panel.png",
    "social_infrastructure": "figures/social_infrastructure_santiago_4panel.png",
    "food_environment": "figures/food_environment_santiago_4panel.png",
    "wind": "figures/wind_santiago_4panel.png",
}

RUN_COMMANDS = {
    "air_quality": "python scripts/run_air_quality.py",
    "air_quality_satellite": "python scripts/run_air_quality_satellite.py",
    "air_quality_pm25": "python scripts/run_pm25.py",
    "climate_openmeteo": "python scripts/run_climate_metrics.py --daily-csv data/processed/santiago_climate_era5land_daily_2015_2024.csv",
}

VALIDATION_SPECS = [
    {
        "name": "greenspace_cv",
        "csv": "santiago_greenspace_cv_commune.csv",
        "geojson": "santiago_greenspace_cv_sample.geojson",
        "columns": ["cv_green_pct_mean", "cv_green_pct_std", "osm_green_pct_mean", "cv_outside_osm_pct_mean", "n_samples"],
        "category": "validation",
        "run_command": "python scripts/run_greenspace_cv.py --method exg --samples-per-commune 5",
    },
    {
        "name": "neuro_mortality",
        "csv": "santiago_neuro_mortality_2018_2022.csv",
        "geojson": "santiago_neuro_mortality_2018_2022.geojson",
        "columns": ["outcome", "mortality_rate_crude_per_100k", "mortality_rate_age_adjusted_per_100k"],
        "category": "comparator",
        "run_command": "python scripts/run_neuro_mortality.py",
    },
    {
        "name": "neuro_hospitalizations",
        "csv": "santiago_neuro_hospitalizations_2006_2006.csv",
        "geojson": "santiago_neuro_hospitalizations_2006_2006.geojson",
        "columns": ["outcome", "hospital_rate_crude_per_100k", "hospital_rate_age_adjusted_per_100k"],
        "category": "comparator",
        "run_command": "python scripts/run_neuro_hospitalizations.py",
    },
]


@dataclass(frozen=True)
class CsvAudit:
    rows: int | None
    unique_names: int | None
    duplicate_names: str
    missing_names: int | None
    missing_required_columns: list[str]


@dataclass(frozen=True)
class StudyAudit:
    study_id: str
    location: str
    country_code: str
    mode: str
    unit_type: str
    expected_units: int | None
    observed_units: int | None
    spatial_path: str
    spatial_exists: bool
    paths: dict[str, str]
    master_outputs: dict[str, str]
    enabled_layers: tuple[str, ...]

    @property
    def status(self) -> str:
        if not self.spatial_exists:
            return "missing_spatial_input"
        if self.mode == "native":
            return "ready"
        if (
            self.expected_units is not None
            and self.observed_units is not None
            and self.observed_units != self.expected_units
        ):
            return "unit_count_issue"
        return "ready"


def rel(path: Path | str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(ROOT).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def count_geojson_units(path: Path) -> int | None:
    """Return a cheap feature count for GeoJSON inputs without loading geopandas."""
    if not path.exists() or path.suffix.lower() not in {".geojson", ".json"}:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    features = payload.get("features") if isinstance(payload, dict) else None
    return len(features) if isinstance(features, list) else None


def build_study_audit(study_ref: str | Path) -> StudyAudit:
    """Resolve one multi-location study without changing the legacy dashboard."""
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from exposome.studies import load_study

    context = load_study(study_ref, repo_root_path=ROOT)
    spatial_path = context.spatial_path
    master_dir = context.paths.processed
    return StudyAudit(
        study_id=context.study.id,
        location=context.location.name,
        country_code=context.country_code,
        mode=context.mode,
        unit_type=context.study.unit_type,
        expected_units=context.expected_units,
        observed_units=None if context.is_native else count_geojson_units(spatial_path),
        spatial_path=rel(spatial_path),
        spatial_exists=spatial_path.exists(),
        paths={name: rel(path) for name, path in context.paths.to_dict().items()},
        master_outputs={
            name: rel(master_dir / filename)
            for name, filename in {
                "csv": "master.csv",
                "geojson": "master.geojson",
                "coverage": "master_coverage.csv",
                "metadata": "master_metadata.json",
            }.items()
        },
        enabled_layers=context.enabled_layers,
    )


def format_study_audit(report: StudyAudit) -> str:
    expected = str(report.expected_units) if report.expected_units is not None else "dynamic"
    observed = str(report.observed_units) if report.observed_units is not None else "not_inspected"
    lines = [
        f"Study: {report.study_id}",
        f"Status: {report.status}",
        f"Location: {report.location} ({report.country_code})",
        f"Mode: {report.mode}",
        f"Spatial unit: {report.unit_type}",
        f"Expected units: {expected}",
        f"Observed units: {observed}",
        f"Spatial input: {report.spatial_path} ({'found' if report.spatial_exists else 'missing'})",
        "Paths:",
    ]
    lines.extend(f"  {name}: {path}" for name, path in report.paths.items())
    lines.append("Master outputs:")
    lines.extend(f"  {name}: {path}" for name, path in report.master_outputs.items())
    lines.append("Enabled layers: " + ", ".join(report.enabled_layers))
    return "\n".join(lines)


def load_layer_specs(path: Path = ROOT / "scripts" / "build_master_exposome.py") -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "LAYER_SPECS":
                    specs = evaluate_static_ast(node.value)
                    if not isinstance(specs, list):
                        raise ValueError("LAYER_SPECS is not a list")
                    return specs
    raise ValueError(f"LAYER_SPECS not found in {path}")


def evaluate_static_ast(node: ast.AST, variables: dict[str, Any] | None = None) -> Any:
    """Evaluate literals and simple comprehensions used by ``LAYER_SPECS``."""
    values = dict(variables or {})
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [evaluate_static_ast(item, values) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(evaluate_static_ast(item, values) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            evaluate_static_ast(key, values): evaluate_static_ast(value, values)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.Name) and node.id in values:
        return values[node.id]
    if isinstance(node, ast.JoinedStr):
        return "".join(str(evaluate_static_ast(item, values)) for item in node.values)
    if isinstance(node, ast.FormattedValue):
        value = evaluate_static_ast(node.value, values)
        if node.format_spec is None:
            return value
        return format(value, str(evaluate_static_ast(node.format_spec, values)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
        if node.keywords:
            raise ValueError("range keywords are not supported in LAYER_SPECS")
        args = [evaluate_static_ast(arg, values) for arg in node.args]
        return range(*args)
    if isinstance(node, ast.ListComp):
        expanded: list[Any] = []

        def visit_generator(index: int, local_values: dict[str, Any]) -> None:
            if index == len(node.generators):
                expanded.append(evaluate_static_ast(node.elt, local_values))
                return
            generator = node.generators[index]
            if generator.is_async or generator.ifs or not isinstance(generator.target, ast.Name):
                raise ValueError("Only simple static comprehensions are supported in LAYER_SPECS")
            for item in evaluate_static_ast(generator.iter, local_values):
                next_values = dict(local_values)
                next_values[generator.target.id] = item
                visit_generator(index + 1, next_values)

        visit_generator(0, values)
        return expanded
    raise ValueError(f"Unsupported static expression in LAYER_SPECS: {ast.dump(node)}")


def audit_csv(path: Path, required_columns: list[str]) -> CsvAudit:
    if not path.exists():
        return CsvAudit(None, None, "", None, required_columns)

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing_required = [col for col in required_columns if col not in header]
        rows = list(reader)

    names = [row.get("name", "") for row in rows]
    nonempty_names = [name for name in names if str(name).strip()]
    duplicate_names = sorted({name for name in nonempty_names if nonempty_names.count(name) > 1})
    return CsvAudit(
        rows=len(rows),
        unique_names=len(set(nonempty_names)) if "name" in header else None,
        duplicate_names="; ".join(duplicate_names),
        missing_names=len(rows) - len(nonempty_names) if "name" in header else None,
        missing_required_columns=missing_required,
    )


def default_geojson_name(csv_name: str) -> str:
    return csv_name.removesuffix(".csv") + ".geojson"


def metadata_path_for(csv_name: str) -> Path:
    stem = csv_name.removesuffix(".csv")
    candidates = [
        DATA_DIR / f"{stem}_metadata.json",
        DATA_DIR / f"{stem}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_methodology(layer_id: str) -> str:
    if layer_id in METHODOLOGY_DOCS:
        return METHODOLOGY_DOCS[layer_id]
    close = difflib.get_close_matches(layer_id, METHODOLOGY_DOCS, n=1, cutoff=0.74)
    return METHODOLOGY_DOCS[close[0]] if close else ""


def resolve_figure(layer_id: str) -> str:
    return FIGURES.get(layer_id, "")


def run_command_for(layer_id: str) -> str:
    if layer_id in RUN_COMMANDS:
        return RUN_COMMANDS[layer_id]
    return f"python scripts/run_{layer_id}.py"


def status_for(row: dict[str, str]) -> str:
    required = row["required_or_optional"] == "required"
    has_csv = bool(row["csv_path"]) and (ROOT / row["csv_path"]).exists()
    rows_ok = (
        row["rows"] == row["expected_rows"]
        if row["category"] in {"master_required", "master_optional", "validation", "multicity"}
        else has_csv
    )
    names_ok = row["missing_names"] in {"", "0"} and (row["duplicate_names"] == "" or row["category"] == "comparator")
    columns_ok = row["required_columns_ok"] == "true"
    master_ok = row["in_master"] == "true" or row["category"] in {"validation", "comparator", "multicity"}

    if required and not has_csv:
        return "missing_required_output"
    if not has_csv:
        return "missing_optional_output"
    if row["layer_id"] == "noise_spain" and not (
        ROOT
        / "data/processed/es/barcelona/barcelona_districts_noise/detail/noise_lden.vector_contours.json"
    ).is_file():
        return "missing_vector_detail"
    if not columns_ok:
        return "missing_required_columns"
    if not names_ok:
        return "name_integrity_issue"
    if not rows_ok:
        return "row_count_issue"
    if not master_ok:
        return "not_in_master"
    return "ready_for_review"


def _canonical_context(study_ref: str = DEFAULT_STUDY) -> Any:
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from exposome.studies import load_study

    return load_study(study_ref, repo_root_path=ROOT)


def _manifest_paths(output_dir: Path) -> dict[str, Path]:
    """Read declared assets instead of guessing output filenames."""
    manifest = output_dir / "manifest.json"
    if not manifest.is_file():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    paths: dict[str, Path] = {}
    for key, role in (("csv", "primary_table"), ("geojson", "primary_geometry")):
        value = payload.get(role)
        if value:
            paths[key] = output_dir / str(value)
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict) or not asset.get("path"):
            continue
        role = str(asset.get("role", ""))
        path = output_dir / str(asset["path"])
        if role == "metadata":
            paths["metadata"] = path
        media_type = str(asset.get("media_type", ""))
        if "figure" not in paths and (
            media_type.startswith("image/") or path.suffix.lower() == ".pdf"
        ):
            paths["figure"] = path
    return paths


def master_columns(study_ref: str = DEFAULT_STUDY) -> set[str]:
    path = _canonical_context(study_ref).paths.processed / "master.csv"
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return set(next(csv.reader(handle), []))


def build_rows(study_ref: str = DEFAULT_STUDY) -> list[dict[str, str]]:
    """Build the Santiago review dashboard from canonical layer manifests."""
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from exposome.layers import load_layer_catalog

    context = _canonical_context(study_ref)
    catalog = load_layer_catalog()
    master_cols = master_columns(study_ref)
    rows: list[dict[str, str]] = []

    layer_ids = tuple(dict.fromkeys(catalog.resolve_id(layer_id) for layer_id in context.enabled_layers))
    for layer_id in layer_ids:
        spec = catalog.get(layer_id)
        master = dict(spec.master or {})
        category = "comparator" if spec.category.value == "comparator" else (
            "master_optional" if master.get("optional_layer", False) else "master_required"
        )
        if layer_id == "greenspace_cv":
            category = "validation"
        paths = _manifest_paths(context.paths.layer_processed(layer_id))
        csv_path = paths.get("csv", context.paths.layer_processed(layer_id) / "missing.csv")
        geojson_path = paths.get("geojson", context.paths.layer_processed(layer_id) / "missing.geojson")
        required_columns = ["spatial_id", *master.get("required_columns", ())]
        audit = audit_csv(csv_path, required_columns)
        output_columns = [master.get("rename", {}).get(col, col) for col in master.get("required_columns", ())]
        in_master = bool(master_cols) and all(col in master_cols for col in output_columns)
        optional = category != "master_required"

        row = {
            "layer_id": layer_id,
            "factor": FACTOR_LABELS.get(layer_id, layer_id.replace("_", " ").title()),
            "category": category,
            "required_or_optional": "optional" if optional else "required",
            "run_command": f"exposome run --study {study_ref} --layers {layer_id} --resume",
            "csv_path": rel(csv_path),
            "geojson_path": rel(geojson_path),
            "metadata_path": rel(paths.get("metadata")),
            "methodology_doc": resolve_methodology(layer_id),
            "figure_or_map": rel(paths.get("figure")),
            "rows": "" if audit.rows is None else str(audit.rows),
            "expected_rows": str(context.expected_units or "") if category != "comparator" else "",
            "unique_names": "" if audit.unique_names is None else str(audit.unique_names),
            "duplicate_names": audit.duplicate_names,
            "missing_names": "" if audit.missing_names is None else str(audit.missing_names),
            "required_columns_ok": "true" if not audit.missing_required_columns else "false",
            "missing_required_columns": "; ".join(audit.missing_required_columns),
            "in_master": "not_applicable" if category in {"validation", "comparator"} else ("true" if in_master else "false"),
        }
        row["auto_status"] = status_for(row)
        rows.append(with_manual_defaults(row))
    if study_ref == DEFAULT_STUDY:
        rows.append(_noise_spain_row(catalog))
    return rows


def _noise_spain_row(catalog: Any) -> dict[str, str]:
    """Track the Barcelona MVT gate alongside the canonical layer dashboard."""
    context = _canonical_context("barcelona_districts_noise")
    layer_id = "noise_spain"
    spec = catalog.get(layer_id)
    master = dict(spec.master or {})
    paths = _manifest_paths(context.paths.layer_processed(layer_id))
    csv_path = paths.get("csv", context.paths.layer_processed(layer_id) / "missing.csv")
    geojson_path = paths.get(
        "geojson", context.paths.layer_processed(layer_id) / "missing.geojson"
    )
    required_columns = ["spatial_id", *master.get("required_columns", ())]
    audit = audit_csv(csv_path, required_columns)
    detail = context.paths.processed / "detail" / "noise_lden.vector_contours.json"
    row = {
        "layer_id": layer_id,
        "factor": FACTOR_LABELS[layer_id],
        "category": "multicity",
        "required_or_optional": "required",
        "run_command": (
            "python scripts/build_noise_vector_tiles.py "
            "--study barcelona_districts_noise --resume"
        ),
        "csv_path": rel(csv_path),
        "geojson_path": rel(geojson_path),
        "metadata_path": rel(paths.get("metadata")),
        "methodology_doc": METHODOLOGY_DOCS[layer_id],
        "figure_or_map": rel(detail),
        "rows": "" if audit.rows is None else str(audit.rows),
        "expected_rows": str(context.expected_units or ""),
        "unique_names": "" if audit.unique_names is None else str(audit.unique_names),
        "duplicate_names": audit.duplicate_names,
        "missing_names": "" if audit.missing_names is None else str(audit.missing_names),
        "required_columns_ok": "true" if not audit.missing_required_columns else "false",
        "missing_required_columns": "; ".join(audit.missing_required_columns),
        "in_master": "not_applicable",
    }
    row["auto_status"] = status_for(row)
    return with_manual_defaults(row)


def with_manual_defaults(row: dict[str, str]) -> dict[str, str]:
    row = dict(row)
    row.update(
        {
            "review_status": "not_started",
            "review_tool": "",
            "review_date": "",
            "review_doc": f"docs/review_prompts/{row['layer_id']}.md",
            "blockers": "",
            "next_action": "Abrir sesion de revision con el prompt de la capa.",
            "final_check": "false",
        }
    )
    return row


def read_manual_fields(path: Path = STATUS_CSV) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row["layer_id"]: {field: row.get(field, "") for field in MANUAL_FIELDS} for row in reader}


def merge_manual(rows: list[dict[str, str]], manual: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    merged = []
    for row in rows:
        if row["layer_id"] in manual:
            row = dict(row)
            for field in MANUAL_FIELDS:
                value = manual[row["layer_id"]].get(field, "")
                if value != "":
                    row[field] = value
            merged.append(row)
        else:
            merged.append(row)
    return merged


def write_csv(rows: list[dict[str, str]], path: Path = STATUS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in CSV_FIELDS} for row in rows])


def md_link(path: str) -> str:
    if not path:
        return ""
    exists = (ROOT / path).exists()
    label = Path(path).name
    text = f"[{label}](../{path})" if path.startswith(("data/", "figures/", "maps/")) else f"[{label}]({path.removeprefix('docs/')})"
    if path.startswith("docs/review_prompts/"):
        return text
    return text if exists else f"`missing: {path}`"


def write_markdown(rows: list[dict[str, str]], path: Path = STATUS_MD) -> None:
    groups = [
        ("Capas requeridas en master", "master_required"),
        ("Capas opcionales en master", "master_optional"),
        ("Validaciones", "validation"),
        ("Comparadores sanitarios", "comparator"),
        ("Capas multiciudad", "multicity"),
    ]
    lines = [
        "# Estado de exposomas",
        "",
        "Tablero operativo del release canónico `santiago_communes` y de gates multiciudad para revisar cada capa en sesiones separadas.",
        "Regenerar con `exposome audit --study santiago_communes` y `python scripts/audit_exposome_status.py --write` desde la raíz.",
        "",
        "Los enlaces de salida se declaran por `manifest.json`; la entrega completa se comprueba con "
        "`exposome verify --study santiago_communes`.",
        "",
        "Estados manuales permitidos: `not_started`, `in_review`, `partial`, `checked`, `blocked`, `not_applicable`.",
        "Una fila recibe `final_check=true` solo despues de la revision metodologica y reproducible de la capa.",
        "",
    ]

    rendered_titles: set[str] = set()
    for title, category in groups:
        subset = [row for row in rows if row["category"] == category]
        if not subset:
            continue
        if title not in rendered_titles:
            lines.extend([f"## {title}", ""])
            rendered_titles.add(title)
        lines.extend(
            [
                "| Capa | Auto | Review | Check | CSV | Metodo | Prompt | Siguiente accion |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for row in subset:
            lines.append(
                "| "
                + " | ".join(
                    [
                        row["layer_id"],
                        row["auto_status"],
                        row["review_status"],
                        row["final_check"],
                        md_link(row["csv_path"]),
                        md_link(row["methodology_doc"]),
                        md_link(row["review_doc"]),
                        row["next_action"].replace("|", "/"),
                    ]
                )
                + " |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def prompt_text(row: dict[str, str]) -> str:
    master_note = "Debe verificarse integración en `master.csv` y en el `release_manifest.json` del estudio."
    row_note = "Confirmar que el CSV existe, tiene 52 unidades y `spatial_id` sin duplicados ni faltantes."
    if row["category"] in {"validation", "comparator"}:
        master_note = "No es una capa del master; revisar su rol como validacion/comparador y sus cruces con el master."
    if row["category"] == "comparator":
        row_note = "Confirmar que el CSV existe, contiene comunas validas y permite multiples filas por comuna cuando hay varios outcomes."
    if row["category"] == "multicity":
        row_note = (
            f"Confirmar que el CSV del gate existe, tiene {row['expected_rows']} unidades, "
            "`spatial_id` íntegro y un descriptor de detalle verificable."
        )
        master_note = (
            "Debe verificarse materialización, publicación y `spatial-audit --strict` "
            "del estudio gate antes del rollout."
        )
    if row["layer_id"] == "air_quality":
        row_note = (
            "Confirmar que el CSV legacy existe, tiene 52 comunas, conserva PM2.5 solo como comparador "
            "y que `name` no tiene duplicados ni faltantes."
        )
        master_note = "Confirmar que el master contiene `n_grid` y `no2_who_ratio`, nunca PM2.5 CAMS."
    return f"""# Revision de capa: {row['layer_id']}

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `{row['factor']}` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `{row['run_command']}`
- CSV: `{row['csv_path']}`
- GeoJSON: `{row['geojson_path']}`
- Metadata: `{row['metadata_path']}`
- Metodologia: `{row['methodology_doc'] or 'pendiente'}`
- Figura/mapa: `{row['figure_or_map'] or 'pendiente'}`

## Checklist
- {row_note}
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- {master_note}
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: {row['layer_id']}
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
"""


def write_prompts(rows: list[dict[str, str]], prompts_dir: Path = PROMPTS_DIR) -> None:
    prompts_dir.mkdir(parents=True, exist_ok=True)
    template = """# Plantilla de revision de exposoma

Abrir una sesion por capa. Pegar el prompt especifico de `docs/review_prompts/<layer_id>.md`.

Criterio de check:
- Output tabular valido y completo.
- Reproducibilidad documentada.
- Metodologia, unidades, fuentes y limitaciones claras.
- Integracion al master cuando aplica.
- Figura/mapa o diagnostico visual suficiente cuando aplica.
"""
    (prompts_dir / "_template.md").write_text(template, encoding="utf-8")
    for row in rows:
        (prompts_dir / f"{row['layer_id']}.md").write_text(prompt_text(row), encoding="utf-8")


def current_serialized(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def generated_outputs(rows: list[dict[str, str]]) -> tuple[str, str]:
    tmp_csv = ROOT / "tmp" / "_exposome_status_preview.csv"
    tmp_md = ROOT / "tmp" / "_exposome_status_preview.md"
    tmp_csv.parent.mkdir(exist_ok=True)
    write_csv(rows, tmp_csv)
    write_markdown(rows, tmp_md)
    csv_text = tmp_csv.read_text(encoding="utf-8")
    md_text = tmp_md.read_text(encoding="utf-8")
    tmp_csv.unlink(missing_ok=True)
    tmp_md.unlink(missing_ok=True)
    return csv_text, md_text


def check_outputs(rows: list[dict[str, str]]) -> list[str]:
    errors = []
    csv_text, md_text = generated_outputs(rows)
    if current_serialized(STATUS_CSV) != csv_text:
        errors.append(f"{rel(STATUS_CSV)} is out of date; run --write")
    if current_serialized(STATUS_MD) != md_text:
        errors.append(f"{rel(STATUS_MD)} is out of date; run --write")

    for row in rows:
        prompt_path = PROMPTS_DIR / f"{row['layer_id']}.md"
        expected = prompt_text(row)
        if current_serialized(prompt_path) != expected:
            errors.append(f"{rel(prompt_path)} is out of date; run --write")

    for row in rows:
        if row["required_or_optional"] == "required" and row["auto_status"] != "ready_for_review":
            errors.append(f"{row['layer_id']} is required but auto_status={row['auto_status']}")
    return errors


def load_metadata_summary() -> dict[str, Any]:
    path = _canonical_context().paths.processed / "master_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit and generate exposome status documentation.")
    parser.add_argument("--write", action="store_true", help="Write docs/exposome_status.{csv,md} and review prompts.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files are out of date or required layers are not ready.")
    parser.add_argument(
        "--study",
        help=(
            "Report the resolved polygons, expected_units, canonical paths and master "
            "outputs for a study in config/studies/."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.study:
        if args.write:
            print("ERROR: --write is only available for the legacy Santiago dashboard.", file=sys.stderr)
            return 2
        report = build_study_audit(args.study)
        print(format_study_audit(report))
        if args.check and report.status != "ready":
            print(
                f"ERROR: study {report.study_id} has status={report.status}",
                file=sys.stderr,
            )
            return 1
        return 0

    rows = merge_manual(build_rows(), read_manual_fields())
    if args.write:
        write_csv(rows)
        write_prompts(rows)
        write_markdown(rows)
        meta = load_metadata_summary()
        shape = (
            f"{meta.get('n_spatial_units', '?')} spatial units, "
            f"{meta.get('n_variables_including_identifiers_area', '?')} columns"
        )
        print(f"Wrote {rel(STATUS_CSV)}, {rel(STATUS_MD)}, and {len(rows)} prompts ({shape}).")

    if args.check:
        errors = check_outputs(rows)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("Exposome status documentation is up to date.")

    if not args.write and not args.check:
        for row in rows:
            print(f"{row['layer_id']}: {row['auto_status']} ({row['rows'] or 'missing'} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
