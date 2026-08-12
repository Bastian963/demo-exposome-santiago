"""Run validation metrics for OSM, strict CV, refined CV and hybrid greenspace masks."""
from __future__ import annotations

import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_validation import run_validation  # noqa: E402

app = typer.Typer(help="Compare greenspace methods against manual labels.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name."),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory."),
    validation_dir: Path = typer.Option(Path("data/validation"), help="Validation working directory."),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output metrics directory."),
    include_examples: bool = typer.Option(True, help="Write per-site diagnostic panels."),
) -> None:
    metrics_path, summary_path = run_validation(
        city=city,
        cache_dir=cache_dir,
        validation_dir=validation_dir,
        out_dir=out_dir,
        include_examples=include_examples,
    )
    decision_path = Path(out_dir) / f"{city}_greenspace_cv_validation_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))["decision"]
    print(f"Wrote {metrics_path}")
    print(f"Wrote {summary_path}")
    print(f"Decision: {decision}")


if __name__ == "__main__":
    app()
