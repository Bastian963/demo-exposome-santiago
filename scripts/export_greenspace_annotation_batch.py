"""Export a compact manifest for one annotation batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome.greenspace_validation import (  # noqa: E402
    _batch_paths,
    _sites_paths,
    build_annotation_batch_manifest,
    build_annotation_queue,
)

app = typer.Typer(help="Export a compact per-batch annotation manifest.")


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows_"
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in df.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


@app.command()
def run(
    batch_id: str = typer.Option("", help="Batch id to export; defaults to the next pending batch."),
    validation_dir: Path = typer.Option(Path("data/validation"), help="Validation working directory."),
) -> None:
    site_paths = _sites_paths(validation_dir)
    sites = pd.read_csv(site_paths.sites_csv)
    queue = build_annotation_queue(sites, site_paths.labels_dir, site_paths.second_pass_dir)
    batch_queue, summary = build_annotation_batch_manifest(queue, batch_id=batch_id or None)
    if not summary["batch_id"]:
        print("No pending annotation tasks.")
        raise typer.Exit(code=0)

    paths = _batch_paths(validation_dir, summary["batch_id"])
    paths.batch_dir.mkdir(parents=True, exist_ok=True)
    batch_queue.to_csv(paths.manifest_csv, index=False)

    lines = [
        f"# Annotation Batch {summary['batch_id']}",
        "",
        f"- pending_tasks: `{summary['n_pending_tasks']}`",
        f"- primary_pending: `{summary['n_primary_pending']}`",
        f"- second_pass_pending: `{summary['n_second_pass_pending']}`",
        f"- unique_sites: `{summary['n_unique_sites']}`",
        f"- next_site_id: `{summary['next_site_id']}`",
        "",
        "## Files",
        "",
        f"- manifest: `{paths.manifest_csv}`",
        f"- source queue: `{validation_dir / 'greenspace_cv' / 'greenspace_cv_annotation_queue.csv'}`",
        "",
        "## First rows",
        "",
    ]
    preview_cols = [
        "site_id",
        "comuna",
        "stratum",
        "task_type",
        "batch_position",
        "image_path",
        "label_path",
    ]
    preview = _markdown_table(batch_queue[preview_cols].head(10))
    lines.append(preview)
    paths.readme_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {paths.manifest_csv}")
    print(f"Wrote {paths.readme_md}")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    app()
