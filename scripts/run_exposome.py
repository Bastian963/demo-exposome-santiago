"""Run catalogued exposome layers for a configured spatial study."""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.layers import PreflightError  # noqa: E402
from exposome.pipeline import run_study  # noqa: E402


app = typer.Typer(
    help="Run portable exposome layers for a country/location/study configuration."
)


def _parse_layers(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    layers = tuple(item.strip() for item in value.split(",") if item.strip())
    if not layers:
        raise typer.BadParameter("--layers must contain at least one layer id")
    if len(layers) != len(set(layers)):
        raise typer.BadParameter("--layers contains duplicate ids")
    return layers


@app.command()
def run(
    study: str = typer.Option(
        ...,
        "--study",
        help="Study id or YAML path (for example santiago_communes).",
    ),
    layers: str | None = typer.Option(
        None,
        "--layers",
        help="Comma-separated enabled layer ids; defaults to the study layer list.",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Skip a layer when its directory already contains normalized output.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Execute layers even when normalized output exists; provider caches remain reusable.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print preflight and commands without creating files or contacting providers.",
    ),
    build_master: bool = typer.Option(
        True,
        "--build-master/--no-build-master",
        help="Build the study master after successful layer execution.",
    ),
) -> None:
    """Preflight, execute, normalize, and integrate selected exposome layers."""
    if resume and force:
        raise typer.BadParameter("--resume and --force are mutually exclusive")
    selected = _parse_layers(layers)
    try:
        summary = run_study(
            study,
            layer_ids=selected,
            resume=resume,
            force=force,
            dry_run=True,
            build_master=build_master,
        )
        if summary.context.is_native and build_master:
            typer.echo(
                "Native study: master aggregate disabled; products retain native support. "
                "Use query_exposome.py or aggregate_exposome.py for derived tables."
            )
            build_master = False
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo("Preflight")
    for plan in summary.plans:
        detail = "; ".join(plan.preflight.reasons)
        typer.echo(f"  {plan.layer.id}: {plan.preflight.status.value} - {detail}")

    typer.echo("Execution plan")
    for plan in summary.plans:
        if plan.skip:
            action = "SKIP"
        elif not plan.preflight.runnable:
            action = "BLOCKED"
        else:
            action = "RUN"
        typer.echo(f"  {action} {plan.layer.id}: {shlex.join(plan.command)}")
    if build_master:
        typer.echo(f"  BUILD master: {summary.context.paths.processed}")

    if dry_run:
        payload = {
            "study": summary.context.study.id,
            "dry_run": True,
            "layers": [plan.as_dict() for plan in summary.plans],
            "build_master": build_master,
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        if summary.has_blockers:
            raise typer.Exit(code=2)
        return

    try:
        summary = run_study(
            study,
            layer_ids=selected,
            resume=resume,
            force=force,
            build_master=build_master,
        )
        for result in summary.results:
            typer.echo(f"{result.layer_id}: {result.action} -> {result.output_dir}")
        if summary.master is not None:
            typer.echo(f"master: written -> {summary.context.paths.processed}")
            metadata_path = getattr(summary.master, "paths", {}).get("metadata")
            if metadata_path:
                typer.echo(f"metadata: {metadata_path}")
    except PreflightError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Execution failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
