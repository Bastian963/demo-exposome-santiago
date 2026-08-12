"""Inventory or collect missing annual exposome products for any study.

This is a human-run, resumable command. It never rebuilds a master, publishes
the webapp, or runs health analyses. ``--local-only`` is safe for materializing
already downloaded precipitation/wildfire sources and will never call a remote
adapter.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.studies import load_study  # noqa: E402
from exposome.temporal_exposomes import (  # noqa: E402
    DEFAULT_STUDY,
    collect_missing,
    default_paths,
    duration_hint,
    inventory,
    status_summary,
    validate_no_analysis_side_effects,
)

app = typer.Typer(
    add_completion=False,
    help="Resumable annual-exposome collector for any aggregate study.",
)


@app.command()
def run(
    study: str = typer.Option(
        DEFAULT_STUDY,
        help="Aggregate study id.",
    ),
    status: bool = typer.Option(
        False,
        "--status",
        help="Read-only inventory; make no directories and perform no downloads.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Alias for --status with the full target table.",
    ),
    require_complete: bool = typer.Option(
        False,
        "--require-complete",
        help="Exit nonzero unless every selected annual product is validated complete.",
    ),
    local_only: bool = typer.Option(
        False,
        "--local-only",
        help="Materialize canonical local sources only; never call a remote adapter.",
    ),
    layer: list[str] | None = typer.Option(
        None,
        "--layer",
        help="Limit work to annual layer ids; repeat the option.",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Skip annual products whose manifests and checksums are valid.",
    ),
    output_root: Path | None = typer.Option(
        None,
        help="Optional isolated output root (default: canonical study/temporal_exposomes).",
    ),
    cache_root: Path | None = typer.Option(
        None,
        help="Optional cache root (default: canonical study cache/temporal_exposomes).",
    ),
) -> None:
    """Inventory or collect all reproducible annual exposomes for one study."""
    context = load_study(study, repo_root_path=REPO_ROOT)
    paths = default_paths(context)
    if output_root is not None:
        paths = type(paths)(Path(output_root), paths.cache_root)
    if cache_root is not None:
        paths = type(paths)(paths.output_root, Path(cache_root))
    validate_no_analysis_side_effects(paths)

    try:
        table = inventory(context, paths=paths, layers=layer)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--layer") from exc
    annual = table[table["classification"] == "annual_downloadable"]
    pending = int((annual["state"] == "pending").sum())
    cached = int((annual["state"] == "source_cached").sum())
    complete = int((annual["state"] == "complete").sum())

    typer.echo(status_summary(table))
    typer.echo(
        f"\nTargets: {len(annual)}; complete={complete}; "
        f"source_cached={cached}; pending_download={pending}"
    )
    typer.echo(duration_hint(0 if local_only else pending))
    if dry_run:
        typer.echo("\n" + table.to_string(index=False))
    if status or dry_run:
        if require_complete and complete != len(annual):
            typer.echo(
                f"Annual completeness gate failed: {complete}/{len(annual)} complete.",
                err=True,
            )
            raise typer.Exit(code=2)
        return

    typer.echo(f"\nOutput: {paths.output_root}")
    typer.echo(f"Cache:  {paths.cache_root}")
    try:
        final = collect_missing(
            study=study,
            layers=layer,
            output_root=paths.output_root,
            cache_root=paths.cache_root,
            resume=resume,
            local_only=local_only,
        )
    except RuntimeError as exc:
        typer.echo(f"\nCollection finished with failures: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    final_annual = final[final["classification"] == "annual_downloadable"]
    typer.echo(
        "\nCollection checkpointed: "
        f"{int((final_annual['state'] == 'complete').sum())}/{len(final_annual)} "
        "annual products validated."
    )
    if require_complete and not (final_annual["state"] == "complete").all():
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
