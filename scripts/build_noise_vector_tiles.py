"""Build verified local MVT detail for Spain's SICA/MER Lden contours."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.noise_spain import RAW_DATASET, RAW_PROVIDER  # noqa: E402
from exposome.noise_spain_tiles import build_noise_vector_tiles  # noqa: E402
from exposome.raw_sources import load_source_manifest  # noqa: E402
from exposome.studies import load_study  # noqa: E402


app = typer.Typer(
    help="Build resume-safe Mapbox vector tiles from the frozen SICA/MER snapshot."
)


@app.command()
def run(
    study: str = typer.Option(..., help="Aggregate Spain study id."),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    cache_dir: Path | None = typer.Option(None),
    detail_dir: Path | None = typer.Option(None),
) -> None:
    context = load_study(study, repo_root_path=REPO_ROOT)
    if context.is_native:
        raise typer.BadParameter("Noise vector tiles attach to an aggregate study")
    declared_manifest = context.layer_inputs("noise_spain").get("source_manifest")
    if declared_manifest is None:
        raise typer.BadParameter("Study must declare layer_inputs.noise_spain.source_manifest")
    identity = load_source_manifest(declared_manifest.parent, verify=False)
    if (identity.provider, identity.dataset) != (RAW_PROVIDER, RAW_DATASET):
        raise typer.BadParameter(f"Unexpected noise snapshot manifest: {declared_manifest}")
    snapshot_store = context.paths.provider_snapshot(
        identity.provider,
        identity.dataset,
        identity.version,
    )
    if snapshot_store.manifest_path.resolve() != declared_manifest.resolve():
        raise typer.BadParameter(
            f"Study manifest must be at canonical snapshot root: {snapshot_store.manifest_path}"
        )
    outputs = build_noise_vector_tiles(
        study=context,
        raw_snapshot=snapshot_store,
        cache_dir=cache_dir or context.paths.layer_cache("noise_spain"),
        detail_dir=detail_dir or (context.paths.processed / "detail"),
        resume=resume,
    )
    typer.echo(f"Wrote {outputs.tile_count} tiles")
    typer.echo(f"Descriptor: {outputs.descriptor}")
    typer.echo(f"Validation: {outputs.validation}")


if __name__ == "__main__":
    app()
