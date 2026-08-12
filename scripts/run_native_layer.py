"""Run one native-resolution layer for an AOI study."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.native import export_native_layer  # noqa: E402
from exposome.studies import load_study  # noqa: E402

app = typer.Typer(help="Export one native-resolution exposome product.")


@app.command()
def run(
    study: str = typer.Option(..., "--study"),
    layer: str = typer.Option(..., "--layer"),
) -> None:
    context = load_study(study)
    if not context.is_native:
        raise typer.BadParameter("--study must refer to a native study")
    outputs = export_native_layer(context, layer)
    typer.echo(f"{layer}: wrote {', '.join(str(path) for path in outputs)}")


if __name__ == "__main__":
    app()
