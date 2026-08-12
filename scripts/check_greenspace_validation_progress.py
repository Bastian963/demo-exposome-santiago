"""Summarize manual-labeling progress for greenspace validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome.greenspace_validation import _label_progress, _sites_paths  # noqa: E402

app = typer.Typer(help="Report primary and second-pass labeling progress for greenspace validation.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name."),
    validation_dir: Path = typer.Option(Path("data/validation"), help="Validation working directory."),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output metrics directory."),
) -> None:
    paths = _sites_paths(validation_dir)
    sites = pd.read_csv(paths.sites_csv)
    progress = _label_progress(sites, paths.labels_dir, paths.second_pass_dir)
    metadata_path = Path(out_dir) / f"{city}_greenspace_cv_validation_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    print(f"Sites manifest: {paths.sites_csv}")
    print(f"Total sites: {len(sites)}")
    print(f"Primary labeled: {progress.get('n_primary_labeled', 0)} / {progress.get('n_sites', len(sites))}")
    print(f"Official sample communes covered: {progress.get('official_communes_covered', 0)} / 52")
    print(f"Showcase sites labeled: {progress.get('showcase_sites_labeled', 0)} / {int((sites['source_kind'] == 'showcase').sum())}")
    print(
        f"Second pass labeled: {progress.get('n_second_pass_labeled', 0)} / "
        f"{progress.get('n_second_pass_required', 0)}"
    )
    for row in progress.get("by_stratum", []):
        print(
            f"{row['stratum']}: primary {row['primary_labeled']}/{row['n_sites']} "
            f"({row['primary_completion_pct']:.1f}%), second pass {row['second_pass_labeled']}/"
            f"{row['second_pass_required']} ({row['second_pass_completion_pct']:.1f}%)"
        )
    if progress.get("by_batch"):
        print("By batch:")
        for row in progress["by_batch"]:
            print(
                f"{row['batch_id']}: primary {row['primary_labeled']}/{row['n_sites']} "
                f"({row['primary_completion_pct']:.1f}%), second pass {row['second_pass_labeled']}/"
                f"{row['second_pass_required']} ({row['second_pass_completion_pct']:.1f}%)"
            )
    if metadata:
        print(f"Last validation decision: {metadata.get('decision', 'unknown')}")


if __name__ == "__main__":
    app()
