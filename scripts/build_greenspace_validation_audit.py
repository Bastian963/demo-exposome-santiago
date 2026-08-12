"""Rebuild the consolidated markdown audit for greenspace validation outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_validation import _write_audit_report  # noqa: E402

app = typer.Typer(help="Build a consolidated markdown audit from greenspace validation outputs.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name."),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output metrics directory."),
) -> None:
    out_dir = Path(out_dir)
    decision_path = out_dir / f"{city}_greenspace_cv_validation_decision.json"
    metadata_path = out_dir / f"{city}_greenspace_cv_validation_metadata.json"
    comparison_path = out_dir / f"{city}_greenspace_cv_validation_comparison_summary.csv"
    ranking_path = out_dir / f"{city}_greenspace_cv_validation_method_ranking.csv"
    agreement_path = out_dir / f"{city}_greenspace_cv_validation_annotator_agreement.csv"
    audit_path = out_dir / f"{city}_greenspace_cv_validation_audit.md"

    evaluation = json.loads(decision_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    comparison_df = pd.read_csv(comparison_path) if comparison_path.exists() else pd.DataFrame()
    ranking_df = pd.read_csv(ranking_path) if ranking_path.exists() else pd.DataFrame()
    agreement_df = pd.read_csv(agreement_path) if agreement_path.exists() else pd.DataFrame()

    _write_audit_report(audit_path, evaluation, metadata, comparison_df, ranking_df, agreement_df)
    print(f"Wrote {audit_path}")


if __name__ == "__main__":
    app()
