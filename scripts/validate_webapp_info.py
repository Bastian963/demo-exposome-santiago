"""Gate the webapp info panel: registry coverage and published-bundle checks.

Usage (from the repo root):

    python scripts/validate_webapp_info.py --registry
    python scripts/validate_webapp_info.py --bundles [--study santiago_communes]
    python scripts/validate_webapp_info.py           # both

Errors exit non-zero; warnings (e.g. missing DOIs) never block.
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.info_validation import (  # noqa: E402
    published_bundles,
    validate_bundle,
    validate_registry,
)

app = typer.Typer(add_completion=False)


@app.command()
def main(
    registry: bool = typer.Option(False, "--registry", help="Validate config/layer_info"),
    bundles: bool = typer.Option(False, "--bundles", help="Validate published bundles"),
    study: str = typer.Option(None, "--study", help="Only bundles for this study id"),
    show_warnings: bool = typer.Option(True, "--warnings/--no-warnings"),
) -> None:
    if not registry and not bundles:
        registry = bundles = True
    errors: list[str] = []
    warnings: list[str] = []
    if registry:
        reg_errors, reg_warnings = validate_registry(REPO_ROOT)
        errors += reg_errors
        warnings += reg_warnings
    if bundles:
        targets = published_bundles(REPO_ROOT)
        if study:
            targets = [bundle for bundle in targets if bundle.name == study]
            if not targets:
                typer.echo(f"no published bundle found for study {study!r}")
                raise typer.Exit(code=1)
        for bundle in targets:
            bundle_errors, bundle_warnings = validate_bundle(bundle)
            errors += bundle_errors
            warnings += bundle_warnings
    for message in errors:
        typer.echo(f"ERROR: {message}")
    if show_warnings:
        for message in warnings:
            typer.echo(f"warning: {message}")
    typer.echo(f"{len(errors)} errors, {len(warnings)} warnings")
    if errors:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
