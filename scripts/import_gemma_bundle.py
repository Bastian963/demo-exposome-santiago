"""Verify and install an AnyDesk-transferred published bundle into local GEMMA."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.gemma_handoff import import_handoff, inspect_handoff  # noqa: E402

app = typer.Typer(help="Import a hash-verified published bundle into local GEMMA data.")


@app.command()
def main(
    archive: Path = typer.Option(..., exists=True, dir_okay=False),
    data_root: Path = typer.Option(REPO_ROOT / "webapp" / "public" / "data"),
    replace: bool = typer.Option(False, help="Replace an existing divergent bundle after verification."),
    inspect_only: bool = typer.Option(False, help="Validate archive only; do not write files."),
) -> None:
    """Check every file hash before changing the local web data directory."""
    handoff = inspect_handoff(archive)
    if inspect_only:
        typer.echo(f"valid handoff: {handoff['study_id']} -> {handoff['bundle']}")
        return
    result = import_handoff(archive, data_root=data_root, repo_root=REPO_ROOT, replace=replace)
    action = "installed" if result["installed"] else "already installed"
    typer.echo(f"{action} {result['study_id']}: {result['bundle']}")
    typer.echo(f"catalog: {result['catalog']}")


if __name__ == "__main__":
    app()
