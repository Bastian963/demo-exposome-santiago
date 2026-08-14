"""Small stable command surface for the config-driven pipeline."""
from __future__ import annotations

import builtins
import json
from pathlib import Path
import subprocess
import sys

import typer

from . import publishing
from .handoff import export_handoff, import_handoff
from .layers import LayerExecutionError
from .pipeline import materialize_study_release, run_study
from .spatial_detail import build_study_detail
from .spatial_audit import audit_spatial_contract, published_bundle_paths
from .spatial_coverage import audit_spatial_coverage
from .spatial_plan import recovery_plan_for_bundle, recovery_plan_for_study
from .verification import verify_study_release


app = typer.Typer(help="BrainLat exposome pipeline")


def _parse_layers(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    layers = tuple(item.strip() for item in value.split(",") if item.strip())
    if not layers:
        raise typer.BadParameter("--layers must contain at least one layer id")
    if len(layers) != len(set(layers)):
        raise typer.BadParameter("--layers contains duplicate ids")
    return layers


@app.command("handoff-export")
def handoff_export(
    node_id: str = typer.Option(..., "--node-id"),
    study: list[str] = typer.Option(..., "--study"),
    output: str = typer.Option(..., "--output"),
    operations: str | None = typer.Option(None, "--operations"),
    run_id: str | None = typer.Option(None, "--run-id"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Freeze complete Study releases for transfer from a collection node."""
    root = Path(__file__).resolve().parents[2]
    try:
        result = export_handoff(
            node_id=node_id, studies=study, output_root=output, repo_root=root,
            operations=operations, run_id=run_id, dry_run=dry_run,
        )
    except Exception as exc:
        typer.echo(f"Handoff export failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if dry_run:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"handoff: {result}")


@app.command("handoff-import")
def handoff_import(
    handoff: str = typer.Option(..., "--handoff"),
    staging: str = typer.Option(..., "--staging"),
    promote: bool = typer.Option(False, "--promote"),
) -> None:
    """Validate a handoff in staging; promotion is explicit and non-overwriting."""
    root = Path(__file__).resolve().parents[2]
    try:
        result = import_handoff(
            handoff=handoff, repo_root=root, staging_root=staging, promote=promote,
        )
    except Exception as exc:
        typer.echo(f"Handoff import failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("run")
def run(
    study: str = typer.Option(..., "--study"),
    layers: str | None = typer.Option(None, "--layers"),
    resume: bool = typer.Option(False, "--resume"),
    force: bool = typer.Option(False, "--force"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    build_master: bool = typer.Option(True, "--build-master/--no-build-master"),
) -> None:
    """Run the catalogued study pipeline in process."""
    try:
        summary = run_study(
            study,
            layer_ids=_parse_layers(layers),
            resume=resume,
            force=force,
            dry_run=dry_run,
            build_master=build_master,
        )
    except LayerExecutionError as exc:
        # One or more layers raised during execution (e.g. an OSM/Overpass
        # provider outage) -- distinct from a config/preflight problem: some
        # layers may have completed and written outputs before the failure.
        run_summary = getattr(exc, "summary", None)
        if run_summary is not None:
            for plan in run_summary.plans:
                typer.echo(
                    f"{plan.layer.id}: {plan.preflight.status.value} - "
                    f"{'; '.join(plan.preflight.reasons)}"
                )
            for result in run_summary.results:
                typer.echo(f"{result.layer_id}: {result.action} -> {result.output_dir}")
        typer.echo(f"Run failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    for plan in summary.plans:
        typer.echo(
            f"{plan.layer.id}: {plan.preflight.status.value} - "
            f"{'; '.join(plan.preflight.reasons)}"
        )
    if dry_run:
        typer.echo(json.dumps({"study": summary.context.study.id, "layers": [plan.as_dict() for plan in summary.plans]}, indent=2))
        if summary.has_blockers:
            raise typer.Exit(code=2)
        return
    for result in summary.results:
        typer.echo(f"{result.layer_id}: {result.action} -> {result.output_dir}")
    if summary.master is not None:
        typer.echo(f"master: written -> {summary.context.paths.processed}")


@app.command("audit")
def audit(study: str = typer.Option(..., "--study")) -> None:
    """Audit one configured study through the existing status adapter."""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "audit_exposome_status.py"), "--study", study],
        cwd=root,
    )
    if result.returncode:
        raise typer.Exit(result.returncode)


@app.command("detail")
def detail(
    study: str = typer.Option(..., "--study"),
    indicators: str | None = typer.Option(None, "--indicators"),
    resume: bool = typer.Option(False, "--resume"),
) -> None:
    """Build browser COGs from already materialized native study products.

    This command is local post-processing only. It never invokes GEE, OSM or
    another provider; run the companion native study separately when its data
    has not yet been collected.
    """
    try:
        results = build_study_detail(
            study,
            indicators=_parse_layers(indicators),
            resume=resume,
        )
    except Exception as exc:
        typer.echo(f"Spatial detail failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    for result in results:
        source = result.source or "-"
        output = result.output or "-"
        typer.echo(f"{result.indicator_id}: {result.action} ({source} -> {output})")


@app.command("verify")
def verify(study: str = typer.Option(..., "--study")) -> None:
    """Verify the checksum-addressed release for one configured study."""
    result = verify_study_release(study, repo_root_path=Path(__file__).resolve().parents[2])
    if result.ok:
        typer.echo(f"verified {result.study_id}: {result.checked_assets} assets")
        return
    typer.echo(f"release verification failed for {result.study_id}:", err=True)
    for issue in result.issues:
        typer.echo(f"- {issue}", err=True)
    raise typer.Exit(code=2)


@app.command("materialize")
def materialize(study: str = typer.Option(..., "--study")) -> None:
    """Rebuild a master and v2 release from already verified local bundles.

    It never calls GEE, OSM, Open-Meteo or another remote provider.  Use it
    after partial recovery runs and profile export, before verify/publish.
    """
    try:
        summary = materialize_study_release(study)
    except Exception as exc:
        typer.echo(f"Materialization failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"master: written -> {summary.context.paths.processed}")
    typer.echo(f"release: written -> {summary.release_manifest}")


@app.command("spatial-audit")
def spatial_audit(
    bundle: str | None = typer.Option(None, "--bundle", help="Published study-bundle directory"),
    palette: str = typer.Option("webapp/public/palette.json", "--palette"),
    all_bundles: bool = typer.Option(False, "--all", help="Audit every published bundle below webapp/public/data"),
    strict: bool = typer.Option(False, "--strict", help="Require the current spatial schema and full COG provenance"),
) -> None:
    """Validate the browser's support declarations and optional published bundle."""
    root = Path(__file__).resolve().parents[2]
    palette_path = (root / palette).resolve() if not Path(palette).is_absolute() else Path(palette)
    bundle_path = None
    if bundle:
        bundle_path = (root / bundle).resolve() if not Path(bundle).is_absolute() else Path(bundle)
    if all_bundles and bundle:
        raise typer.BadParameter("--all and --bundle cannot be combined")
    if all_bundles:
        roots = [root / "webapp" / "public" / "data"]
        results = [
            audit_spatial_contract(palette_path, bundle_path=path.parent, strict=strict)
            for audit_manifest in roots
            for path in published_bundle_paths(audit_manifest)
        ]
        payload = {"ok": builtins.all(result.ok for result in results), "strict": strict, "bundles": [result.as_dict() for result in results]}
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload["ok"]:
            raise typer.Exit(code=2)
        return
    result = audit_spatial_contract(palette_path, bundle_path=bundle_path, strict=strict)
    typer.echo(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    if not result.ok:
        raise typer.Exit(code=2)


@app.command("resolution-coverage")
def resolution_coverage(
    bundle: str | None = typer.Option(None, "--bundle", help="Published study-bundle directory"),
    all_bundles: bool = typer.Option(False, "--all", help="Audit every published bundle below webapp/public/data"),
    tier: str = typer.Option("preview", "--tier", help="preview permits gaps; production requires every target"),
) -> None:
    """Report whether studies publish the maximum support their methods allow."""
    if tier not in {"preview", "production"}:
        raise typer.BadParameter("--tier must be preview or production")
    root = Path(__file__).resolve().parents[2]
    bundle_path = None
    if bundle:
        bundle_path = (root / bundle).resolve() if not Path(bundle).is_absolute() else Path(bundle)
    if all_bundles and bundle:
        raise typer.BadParameter("--all and --bundle cannot be combined")
    if all_bundles:
        bundles = [
            path.parent
            for path in published_bundle_paths(root / "webapp" / "public" / "data")
        ]
    elif bundle_path is not None:
        bundles = [bundle_path]
    else:
        raise typer.BadParameter("provide --bundle or --all")
    results = [audit_spatial_coverage(path) for path in bundles]
    payload = {
        "ok": tier == "preview" or builtins.all(result.publication_tier == "production" for result in results),
        "requested_tier": tier,
        "bundles": [
            {
                "bundle": str(path),
                "study_id": result.study_id,
                **result.as_dict(),
            }
            for path, result in zip(bundles, results, strict=True)
        ],
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["ok"]:
        raise typer.Exit(code=2)


@app.command("resolution-plan")
def resolution_plan(
    bundle: str | None = typer.Option(None, "--bundle", help="Published study-bundle directory"),
    all_bundles: bool = typer.Option(False, "--all", help="Plan every published bundle below webapp/public/data"),
    study: list[str] = typer.Option([], "--study", help="Configured aggregate study; repeat before first publication"),
    output: str = typer.Option("webapp/public/data", "--output", help="Published data root"),
    version: str = typer.Option("v1", "--version", help="Published data version"),
) -> None:
    """Print human-run, resumable commands for each missing spatial product."""
    root = Path(__file__).resolve().parents[2]
    bundle_path = None
    if bundle:
        bundle_path = (root / bundle).resolve() if not Path(bundle).is_absolute() else Path(bundle)
    selected = sum(bool(value) for value in (all_bundles, bundle, study))
    if selected > 1:
        raise typer.BadParameter("choose exactly one of --all, --bundle or --study")
    if all_bundles:
        output_path = (root / output).resolve() if not Path(output).is_absolute() else Path(output)
        bundles = [path.parent for path in published_bundle_paths(output_path / version)]
    elif bundle_path is not None:
        bundles = [bundle_path]
    elif study:
        payload = {
            "plans": [
                recovery_plan_for_study(
                    item,
                    repo_root=root,
                    output_root=output,
                    version=version,
                ).as_dict()
                for item in study
            ]
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    else:
        raise typer.BadParameter("provide --bundle, --all or --study")
    payload = {
        "plans": [
            recovery_plan_for_bundle(path, repo_root=root).as_dict()
            for path in bundles
        ]
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("catalog")
def catalog(
    output: str = typer.Option("webapp/public/data", "--output"),
    version: str = typer.Option("v1", "--version"),
) -> None:
    """Regenerate the web catalog from already-published study manifests.

    This is metadata-only: it does not collect data or republish a study.
    It is useful after adding catalog-level fields such as publication tier.
    """
    root = Path(__file__).resolve().parents[2]
    output_path = (root / output).resolve() if not Path(output).is_absolute() else Path(output)
    payload = publishing.build_catalog(
        repo_root=root,
        output_root=output_path,
        version=version,
    )
    typer.echo(f"catalog: {publishing.write_catalog(payload, output_path)}")


@app.command("publish")
def publish(
    study: list[str] = typer.Option(..., "--study", help="Study id; repeat for multiple studies"),
    output: str = typer.Option("webapp/public/data", "--output"),
    version: str = typer.Option("v1", "--version"),
    clean: bool = typer.Option(False, "--clean"),
    skip_info_validation: bool = typer.Option(
        False,
        "--skip-info-validation",
        help="Escape hatch: publish even if the info panel contract fails",
    ),
) -> None:
    """Publish study outputs as namespaced web bundles."""
    published = []
    for study_id in study:
        result = publishing.publish_study(
            study_id, output_root=output, version=version, clean=clean
        )
        published.append(result)
        typer.echo(f"published {result.study_id}: {result.path}")
    catalog = publishing.build_catalog(
        repo_root=Path(__file__).resolve().parents[2],
        output_root=output,
        version=version,
    )
    typer.echo(f"catalog: {publishing.write_catalog(catalog, output)}")
    if skip_info_validation:
        return
    from .info_validation import validate_bundle

    errors: list[str] = []
    for result in published:
        bundle_errors, bundle_warnings = validate_bundle(result.path)
        errors += bundle_errors
        for message in bundle_warnings:
            typer.echo(f"warning: {message}")
    for message in errors:
        typer.echo(f"ERROR: {message}")
    if errors:
        typer.echo(
            "info panel contract failed; fix config/layer_info or re-run with "
            "--skip-info-validation"
        )
        raise typer.Exit(code=2)


def _points_from_addresses(
    path: Path, *, geocode: bool, postal_country: str | None, repo_root: Path
):
    """Turn a pasted list into coordinates, geocoding only with an explicit flag.

    Addresses are personal data.  Nothing is sent anywhere unless ``--geocode``
    is passed, and the command says out loud which provider it used.
    """
    import pandas as pd

    from .geocoding import KIND_ADDRESS, NominatimGeocoder, classify_input, geocode_lines

    lines = [line for line in Path(path).read_text().splitlines() if line.strip()]
    if not lines:
        raise typer.BadParameter(f"{path} has no usable lines")

    needs_network = any(
        classify_input(line, postal_country).kind == KIND_ADDRESS for line in lines
    )
    if needs_network and not geocode:
        raise typer.BadParameter(
            "This file contains addresses. Pass --geocode to send them to "
            "OpenStreetMap's Nominatim, or supply lat,lon lines instead, which "
            "never leave this machine."
        )
    geocoder = (
        NominatimGeocoder(cache_dir=repo_root / "cache" / "geocoding")
        if needs_network and geocode
        else None
    )
    if geocoder is not None:
        typer.echo(
            "Geocoding addresses with OpenStreetMap Nominatim "
            "(1 req/s, cached in cache/geocoding/)."
        )
    rows = geocode_lines(
        lines, geocoder=geocoder, postal_country=postal_country,
        allow_network=bool(geocoder),
    )
    frame = pd.DataFrame(rows)
    unresolved = frame[frame["lon"].isna()]
    for row in unresolved.itertuples(index=False):
        typer.echo(f"  unresolved [{row.status}]: {row.input_raw}", err=True)
    resolved = frame[frame["lon"].notna()].reset_index(drop=True)
    if resolved.empty:
        raise typer.BadParameter("No input line resolved to coordinates")
    typer.echo(f"{len(resolved)}/{len(frame)} lines resolved to coordinates")
    return resolved


@app.command("extract-points")
def extract_points_command(
    input: Path | None = typer.Option(None, "--input", help="CSV with id, lon and lat"),
    addresses: Path | None = typer.Option(
        None, "--addresses", help="Text file, one address / lat,lon / postal code per line"
    ),
    geocode: bool = typer.Option(
        False, "--geocode",
        help="Send addresses to the geocoder. They leave this machine; see ADR 0012.",
    ),
    postal_country: str | None = typer.Option(
        None, "--postal-country", help="Two-letter country for bare postal codes"
    ),
    lon: float | None = typer.Option(None, "--lon"),
    lat: float | None = typer.Option(None, "--lat"),
    indicators: str | None = typer.Option(
        None, "--indicators", help="Comma-separated exposome ids; default every published one"
    ),
    radii: str = typer.Option("0,300,500,1000", "--radii", help="Metres; 0 = containing cell"),
    years: str | None = typer.Option(None, "--years", help="Comma-separated; default current epoch"),
    output: Path = typer.Option(Path("data/processed/point_extractions"), "--output"),
    data_root: str = typer.Option("webapp/public/data", "--data-root"),
    source: str = typer.Option("published", "--source", help="published or native"),
    study: str | None = typer.Option(None, "--study", help="Force one study instead of per-point"),
    wide_radius: float | None = typer.Option(None, "--wide-radius", help="Also write a wide pivot"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    id_column: str = typer.Option("id", "--id-column"),
    lon_column: str = typer.Option("lon", "--lon-column"),
    lat_column: str = typer.Option("lat", "--lat-column"),
) -> None:
    """Extract published exposome values at coordinates.

    Reads only local rasters and manifests -- it never contacts GEE, OSM or
    Open-Meteo.  Address geocoding is a separate, opt-in step; this command
    consumes coordinates, because a postal area is not a unique point.
    """
    from tqdm import tqdm

    from .point_artifacts import extraction_plan, run_extraction
    from .point_extraction import load_bundle_catalog
    from .point_query import PointQueryError, read_points

    root = Path(__file__).resolve().parents[2]
    resolved_root = Path(data_root) if Path(data_root).is_absolute() else root / data_root
    if source != "published":
        raise typer.BadParameter(
            "--source native is served by scripts/query_exposome.py; it produces a "
            "layer-keyed table with a different shape (see ADR 0012)"
        )
    if addresses is not None:
        points = _points_from_addresses(
            addresses, geocode=geocode, postal_country=postal_country, repo_root=root
        )
    else:
        try:
            points = read_points(input, lon, lat, id_column, lon_column, lat_column)
        except PointQueryError as error:
            raise typer.BadParameter(str(error)) from error

    radius_values = [float(item) for item in radii.split(",") if item.strip()]
    year_values = [item.strip() for item in years.split(",")] if years else None

    if indicators:
        selected = [item.strip() for item in indicators.split(",") if item.strip()]
    else:
        studies = load_bundle_catalog(resolved_root)
        if study:
            studies = [item for item in studies if item.study_id == study]
        selected = sorted({
            indicator
            for item in studies
            for indicator in (item.manifest.get("spatial_indicators") or {})
        })
        if not selected:
            raise typer.BadParameter("No published indicators found; check --data-root")

    if dry_run:
        plan = extraction_plan(points, selected, radius_values, data_root=resolved_root)
        if plan.empty:
            typer.echo("No point falls inside a published study.")
            raise typer.Exit(code=1)
        typer.echo(plan.to_string(index=False))
        blocked = int((plan["radius_status"] == "sub_observation").sum())
        typer.echo(
            f"\n{len(plan)} combinations; {blocked} would be sub_observation "
            "(delivered, but flagged)."
        )
        return

    result = run_extraction(
        points,
        selected,
        output_dir=output,
        radii=radius_values,
        years=year_values,
        data_root=resolved_root,
        cache_dir=root / "cache" / "point_extractions",
        resume=resume,
        wide_radius=wide_radius,
        progress=lambda items: tqdm(items, desc="points", unit="pt"),
        repo_root=root,
    )
    summary = result["summary"]
    typer.echo(f"long table: {result['long_csv']}")
    typer.echo(f"manifest:   {result['manifest']}")
    typer.echo(
        f"{summary.get('rows', 0)} rows for {summary.get('points', 0)} points "
        f"across {len(summary.get('studies', []))} studies; "
        f"{summary.get('values', 0)} values"
    )
    if result["reused_checkpoints"]:
        typer.echo(f"reused {result['reused_checkpoints']} cached points")
    for flag, count in sorted((summary.get("by_flag") or {}).items()):
        typer.echo(f"  {flag}: {count}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
