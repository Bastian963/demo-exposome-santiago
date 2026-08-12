from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

import yaml


ROOT = Path(__file__).resolve().parents[1]
STATUS_CSV = ROOT / "docs" / "exposome_status.csv"
STUDIES_DIR = ROOT / "config" / "studies"
KNOWLEDGE_DIR = ROOT / "docs" / "knowledge"
GENERATED_DIR = KNOWLEDGE_DIR / "generated"
GENERATED_HEADER = "<!-- GENERATED FILE: do not edit manually -->"

ALLOWED_SHARED_METHODOLOGIES = {
    "docs/precipitation_methodology.md": frozenset({"precipitation", "precipitation_spi"}),
    "docs/neuro_outcomes_methodology.md": frozenset({"neuro_mortality", "neuro_hospitalizations"}),
}

# Study/catalog IDs are not fully uniform yet. Keep aliases explicit so links do
# not silently guess across legacy and canonical names.
LAYER_ID_ALIASES = {
    "pm25": "air_quality_pm25",
}

CONFIG_ALIASES = {
    "air_quality_pm25": "pm25",
}

IMPLEMENTATION_ALIASES = {
    "air_quality_pm25": "pm25",
    "air_quality_satellite": "air_quality",
    "climate_openmeteo": "climate_metrics",
    "greenspace_coverage": "greenspace_satellite",
}

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class Study:
    study_id: str
    config_path: Path
    data: dict[str, object]

    @property
    def layers(self) -> tuple[str, ...]:
        value = self.data.get("layers", [])
        if not isinstance(value, list):
            return ()
        return tuple(str(item) for item in value)


def read_status(path: Path = STATUS_CSV) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_studies(directory: Path = STUDIES_DIR) -> list[Study]:
    studies: list[Study] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        study_id = str(raw.get("id") or path.stem)
        studies.append(Study(study_id=study_id, config_path=path, data=raw))
    return studies


def canonical_layer_id(layer_id: str) -> str:
    return LAYER_ID_ALIASES.get(layer_id, layer_id)


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_inputs(
    rows: list[dict[str, str]],
    studies: list[Study],
    *,
    root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []
    layer_ids = [row.get("layer_id", "").strip() for row in rows]
    duplicates = sorted({item for item in layer_ids if item and layer_ids.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate layer_id values: {', '.join(duplicates)}")
    if any(not item for item in layer_ids):
        errors.append("every status row must have layer_id")

    methodology_layers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        layer_id = row.get("layer_id", "<missing>")
        methodology = row.get("methodology_doc", "").strip()
        if not methodology:
            errors.append(f"{layer_id}: methodology_doc is required")
            continue
        target = root / methodology
        if not _within_root(target, root):
            errors.append(f"{layer_id}: methodology escapes repository: {methodology}")
        elif not target.is_file():
            errors.append(f"{layer_id}: methodology does not exist: {methodology}")
        methodology_layers[methodology].add(layer_id)

    for methodology, actual_layers in sorted(methodology_layers.items()):
        if len(actual_layers) < 2:
            continue
        allowed = ALLOWED_SHARED_METHODOLOGIES.get(methodology)
        if allowed != frozenset(actual_layers):
            errors.append(
                f"undeclared shared methodology {methodology}: "
                + ", ".join(sorted(actual_layers))
            )

    study_ids = [study.study_id for study in studies]
    duplicate_studies = sorted({item for item in study_ids if study_ids.count(item) > 1})
    if duplicate_studies:
        errors.append(f"duplicate study IDs: {', '.join(duplicate_studies)}")
    for study in studies:
        if not study.layers:
            errors.append(f"{study.study_id}: study must declare at least one layer")
        if not _within_root(study.config_path, root):
            errors.append(f"{study.study_id}: config path escapes repository")
    return errors


def _encoded_relative_link(source: Path, target: Path, label: str) -> str:
    relative = Path(os.path.relpath(target, start=source.parent)).as_posix()
    href = quote(relative, safe="/._-#")
    return f"[{label}]({href})"


def _optional_link(source: Path, target: Path, label: str) -> str:
    return _encoded_relative_link(source, target, label) if target.is_file() else f"`{target.as_posix()}`"


def _cell(value: object) -> str:
    return str(value or "—").replace("|", "/").replace("\n", " ")


def _config_path(layer_id: str, root: Path) -> Path:
    config_id = CONFIG_ALIASES.get(layer_id, layer_id)
    specific = root / "config" / "layers" / f"{config_id}.yaml"
    return specific if specific.is_file() else root / "config" / "layers.yaml"


def _implementation_path(layer_id: str, root: Path) -> Path | None:
    module_id = IMPLEMENTATION_ALIASES.get(layer_id, layer_id)
    candidate = root / "src" / "exposome" / f"{module_id}.py"
    return candidate if candidate.is_file() else None


def _related_studies(layer_id: str, studies: list[Study]) -> list[Study]:
    return [
        study
        for study in studies
        if layer_id in {canonical_layer_id(item) for item in study.layers}
    ]


def render_layer_page(
    row: dict[str, str],
    studies: list[Study],
    *,
    root: Path,
    output: Path,
) -> str:
    layer_id = row["layer_id"]
    methodology = root / row["methodology_doc"]
    review = root / row.get("review_doc", "")
    config = _config_path(layer_id, root)
    implementation = _implementation_path(layer_id, root)
    status_dashboard = root / "docs" / "exposome_status.md"
    related = _related_studies(layer_id, studies)

    links = [
        f"- Metodología: {_encoded_relative_link(output, methodology, methodology.name)}",
        f"- Configuración: {_optional_link(output, config, config.name)}",
    ]
    if implementation is not None:
        links.append(f"- Implementación: {_encoded_relative_link(output, implementation, implementation.name)}")
    links.extend(
        [
            f"- Revisión: {_optional_link(output, review, review.name or 'pendiente')}",
            f"- Dashboard: {_encoded_relative_link(output, status_dashboard, 'estado de exposomas')}",
        ]
    )

    study_lines = [
        f"- {_encoded_relative_link(output, root / 'docs' / 'knowledge' / 'generated' / 'studies' / f'{study.study_id}.md', study.study_id)}"
        for study in related
    ] or ["- No aparece directamente en un estudio versionado."]

    artifact_fields = (
        ("CSV", "csv_path"),
        ("GeoJSON", "geojson_path"),
        ("Metadata", "metadata_path"),
        ("Figura", "figure_or_map"),
    )
    artifacts = [f"- {label}: `{row.get(field) or 'no declarado'}`" for label, field in artifact_fields]

    return "\n".join(
        [
            GENERATED_HEADER,
            "---",
            "type: exposome-layer",
            f"layer_id: {json.dumps(layer_id, ensure_ascii=False)}",
            f"category: {json.dumps(row.get('category', ''), ensure_ascii=False)}",
            f"required: {str(row.get('required_or_optional') == 'required').lower()}",
            "generated: true",
            "---",
            "",
            f"# {row.get('factor') or layer_id}",
            "",
            f"Identificador canónico: `{layer_id}`.",
            "",
            "## Fuentes y navegación",
            "",
            *links,
            "",
            "## Estudios",
            "",
            *study_lines,
            "",
            "## Ejecución",
            "",
            f"```bash\n{row.get('run_command') or 'No declarado'}\n```",
            "",
            "## Artefactos esperados",
            "",
            *artifacts,
            "",
            "## Estado",
            "",
            f"- Automático: `{row.get('auto_status') or '—'}`",
            f"- Revisión: `{row.get('review_status') or '—'}`",
            f"- Integrado en master: `{row.get('in_master') or '—'}`",
            f"- Check final: `{row.get('final_check') or '—'}`",
            f"- Bloqueadores: {_cell(row.get('blockers'))}",
            f"- Próxima acción: {_cell(row.get('next_action'))}",
            "",
        ]
    )


def render_study_page(
    study: Study,
    layer_ids: set[str],
    *,
    root: Path,
    output: Path,
) -> str:
    data = study.data
    period = data.get("period") if isinstance(data.get("period"), dict) else {}
    spatial = data.get("spatial") if isinstance(data.get("spatial"), dict) else {}
    layer_lines: list[str] = []
    for configured_id in study.layers:
        canonical_id = canonical_layer_id(configured_id)
        if canonical_id in layer_ids:
            target = output.parent.parent / "layers" / f"{canonical_id}.md"
            layer_lines.append(
                f"- {_encoded_relative_link(output, target, canonical_id)}"
                + (f" (configurado como `{configured_id}`)" if configured_id != canonical_id else "")
            )
        else:
            layer_lines.append(f"- `{configured_id}` (sin ficha en el inventario de Santiago)")

    location = str(data.get("location") or "no declarada")
    mode = str(data.get("mode") or "aggregate")
    start_date = period.get("start_date", "no declarada") if isinstance(period, dict) else "no declarada"
    end_date = period.get("end_date", "no declarada") if isinstance(period, dict) else "no declarada"
    unit_type = spatial.get("unit_type", "no declarada") if isinstance(spatial, dict) else "no declarada"
    expected = spatial.get("expected_units", "no declarado") if isinstance(spatial, dict) else "no declarado"

    return "\n".join(
        [
            GENERATED_HEADER,
            "---",
            "type: exposome-study",
            f"study_id: {json.dumps(study.study_id, ensure_ascii=False)}",
            f"location: {json.dumps(location, ensure_ascii=False)}",
            f"hidden: {str(bool(data.get('hidden', False))).lower()}",
            "generated: true",
            "---",
            "",
            f"# Estudio: {study.study_id}",
            "",
            f"- Configuración: {_encoded_relative_link(output, study.config_path, study.config_path.name)}",
            f"- Ubicación: `{location}`",
            f"- Modalidad: `{mode}`",
            f"- Período: `{start_date}` a `{end_date}`",
            f"- Unidad espacial: `{unit_type}`",
            f"- Unidades esperadas: `{expected}`",
            "",
            "## Capas",
            "",
            *layer_lines,
            "",
            "## Comandos",
            "",
            "```bash",
            f"exposome run --study {study.study_id} --dry-run",
            f"exposome run --study {study.study_id} --resume",
            f"exposome publish --study {study.study_id}",
            f"exposome verify --study {study.study_id}",
            "```",
            "",
            "> Los asistentes no ejecutan recolecciones reales contra proveedores externos.",
            "",
        ]
    )


def render_layer_catalog(rows: list[dict[str, str]], *, output: Path, layer_paths: dict[str, Path]) -> str:
    lines = [
        GENERATED_HEADER,
        "# Catálogo de capas",
        "",
        "Generado desde `docs/exposome_status.csv`.",
        "",
        "| Capa | Factor | Categoría | Revisión | Check final |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda item: (item.get("category", ""), item["layer_id"])):
        link = _encoded_relative_link(output, layer_paths[row["layer_id"]], row["layer_id"])
        lines.append(
            f"| {link} | {_cell(row.get('factor'))} | `{_cell(row.get('category'))}` | "
            f"`{_cell(row.get('review_status'))}` | `{_cell(row.get('final_check'))}` |"
        )
    return "\n".join(lines) + "\n"


def render_methodology_catalog(rows: list[dict[str, str]], *, root: Path, output: Path) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["methodology_doc"]].append(row)
    lines = [
        GENERATED_HEADER,
        "# Catálogo de metodologías",
        "",
        "Cada exposoma auditado debe apuntar a un documento metodológico existente.",
        "",
        "| Metodología | Capas cubiertas |",
        "|---|---|",
    ]
    for methodology, covered_rows in sorted(grouped.items()):
        target = root / methodology
        link = _encoded_relative_link(output, target, target.name)
        layers = ", ".join(f"`{row['layer_id']}`" for row in sorted(covered_rows, key=lambda item: item["layer_id"]))
        lines.append(f"| {link} | {layers} |")
    return "\n".join(lines) + "\n"


def render_study_catalog(studies: list[Study], *, output: Path, study_paths: dict[str, Path]) -> str:
    lines = [
        GENERATED_HEADER,
        "# Catálogo de estudios",
        "",
        "Generado desde `config/studies/*.yaml`.",
        "",
        "| Estudio | Ubicación | Capas | Oculto |",
        "|---|---|---:|---|",
    ]
    for study in studies:
        link = _encoded_relative_link(output, study_paths[study.study_id], study.study_id)
        lines.append(
            f"| {link} | `{_cell(study.data.get('location'))}` | {len(study.layers)} | "
            f"`{str(bool(study.data.get('hidden', False))).lower()}` |"
        )
    return "\n".join(lines) + "\n"


def build_outputs(
    *,
    root: Path = ROOT,
    status_path: Path | None = None,
    studies_dir: Path | None = None,
    generated_dir: Path | None = None,
) -> tuple[dict[Path, str], list[str]]:
    status_path = status_path or root / "docs" / "exposome_status.csv"
    studies_dir = studies_dir or root / "config" / "studies"
    generated_dir = generated_dir or root / "docs" / "knowledge" / "generated"
    expected_generated_dir = root / "docs" / "knowledge" / "generated"
    if generated_dir.resolve() != expected_generated_dir.resolve():
        return {}, [f"generated output must stay in {expected_generated_dir}"]
    rows = read_status(status_path)
    studies = read_studies(studies_dir)
    errors = validate_inputs(rows, studies, root=root)
    if errors:
        return {}, errors

    layer_paths = {row["layer_id"]: generated_dir / "layers" / f"{row['layer_id']}.md" for row in rows}
    study_paths = {study.study_id: generated_dir / "studies" / f"{study.study_id}.md" for study in studies}
    outputs: dict[Path, str] = {}
    for row in rows:
        path = layer_paths[row["layer_id"]]
        outputs[path] = render_layer_page(row, studies, root=root, output=path)
    layer_ids = set(layer_paths)
    for study in studies:
        path = study_paths[study.study_id]
        outputs[path] = render_study_page(study, layer_ids, root=root, output=path)

    layer_catalog = generated_dir / "catalogo-capas.md"
    methodology_catalog = generated_dir / "catalogo-metodologias.md"
    study_catalog = generated_dir / "catalogo-estudios.md"
    outputs[layer_catalog] = render_layer_catalog(rows, output=layer_catalog, layer_paths=layer_paths)
    outputs[methodology_catalog] = render_methodology_catalog(rows, root=root, output=methodology_catalog)
    outputs[study_catalog] = render_study_catalog(studies, output=study_catalog, study_paths=study_paths)
    curated: dict[Path, str] = {}
    knowledge_dir = root / "docs" / "knowledge"
    if knowledge_dir.exists():
        for path in knowledge_dir.rglob("*.md"):
            if generated_dir not in path.parents:
                curated[path] = path.read_text(encoding="utf-8")
    errors.extend(validate_markdown_links({**outputs, **curated}))
    return outputs, errors


def validate_markdown_links(outputs: dict[Path, str]) -> list[str]:
    errors: list[str] = []
    expected_paths = {path.resolve() for path in outputs}
    for source, content in outputs.items():
        for raw_href in MARKDOWN_LINK_RE.findall(content):
            href = raw_href.split("#", 1)[0]
            if not href or "://" in href or href.startswith("mailto:"):
                continue
            target = (source.parent / unquote(href)).resolve()
            if target not in expected_paths and not target.exists():
                errors.append(f"{source}: broken local link: {raw_href}")
    return errors


def stale_generated_paths(outputs: dict[Path, str], generated_dir: Path) -> list[Path]:
    expected = {path.resolve() for path in outputs}
    candidates: list[Path] = []
    for subdir in (generated_dir / "layers", generated_dir / "studies"):
        if subdir.exists():
            candidates.extend(subdir.glob("*.md"))
    return sorted(path for path in candidates if path.resolve() not in expected)


def write_outputs(outputs: dict[Path, str], generated_dir: Path) -> list[Path]:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    removed = stale_generated_paths(outputs, generated_dir)
    for path in removed:
        path.unlink()
    return removed


def check_outputs(outputs: dict[Path, str], generated_dir: Path) -> list[str]:
    errors: list[str] = []
    for path, expected in outputs.items():
        if not path.is_file():
            errors.append(f"missing generated file: {path}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"out-of-date generated file: {path}")
    for path in stale_generated_paths(outputs, generated_dir):
        errors.append(f"orphan generated file: {path}")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the shared Obsidian knowledge catalogs.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write generated catalogs and remove obsolete generated pages.")
    mode.add_argument("--check", action="store_true", help="Check inputs, links and generated outputs without writing.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    outputs, errors = build_outputs()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.write:
        removed = write_outputs(outputs, GENERATED_DIR)
        print(f"Wrote {len(outputs)} Obsidian knowledge files; removed {len(removed)} obsolete files.")
        return 0

    errors = check_outputs(outputs, GENERATED_DIR)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Obsidian knowledge catalog is up to date ({len(outputs)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
