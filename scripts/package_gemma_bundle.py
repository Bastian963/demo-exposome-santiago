"""Create an AnyDesk-transferable archive for one verified GEMMA bundle."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.gemma_handoff import create_handoff  # noqa: E402
from exposome.spatial_audit import audit_spatial_contract  # noqa: E402

app = typer.Typer(help="Package one strict-audited web bundle for manual GEMMA transfer.")


@app.command()
def main(
    bundle: Path = typer.Option(..., exists=True, file_okay=False, help="Published bundle directory."),
    output: Path = typer.Option(..., help="Destination .tar archive."),
    data_root: Path = typer.Option(REPO_ROOT / "webapp" / "public" / "data"),
) -> None:
    """Refuse to package a bundle that does not pass the strict spatial audit."""
    audit = audit_spatial_contract(
        REPO_ROOT / "webapp" / "public" / "palette.json", bundle_path=bundle, strict=True
    )
    if not audit.ok:
        for issue in audit.issues:
            typer.echo(f"spatial audit: {issue}", err=True)
        raise typer.Exit(2)
    handoff = create_handoff(bundle, output, data_root=data_root)
    typer.echo(f"packaged {handoff['study_id']}: {output}")
    typer.echo(f"files: {len(handoff['files'])}; manifest: {handoff['manifest_sha256']}")


if __name__ == "__main__":
    app()
