"""Export pending annotation tasks for greenspace validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome.greenspace_validation import (  # noqa: E402
    _queue_paths,
    _sites_paths,
    build_annotation_queue,
)

app = typer.Typer(help="Export pending primary and second-pass annotation tasks.")


@app.command()
def run(
    validation_dir: Path = typer.Option(Path("data/validation"), help="Validation working directory."),
) -> None:
    site_paths = _sites_paths(validation_dir)
    queue_paths = _queue_paths(validation_dir)
    sites = pd.read_csv(site_paths.sites_csv)
    queue = build_annotation_queue(sites, site_paths.labels_dir, site_paths.second_pass_dir)
    queue_paths.queue_csv.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(queue_paths.queue_csv, index=False)

    if queue.empty:
        summary = {
            "n_pending_tasks": 0,
            "n_primary_pending": 0,
            "n_second_pass_pending": 0,
            "recommended_next_batch": "",
            "recommended_next_task_type": "",
        }
    else:
        next_row = queue.iloc[0]
        summary = {
            "n_pending_tasks": int(len(queue)),
            "n_primary_pending": int((queue["task_type"] == "primary").sum()),
            "n_second_pass_pending": int((queue["task_type"] == "second_pass").sum()),
            "recommended_next_batch": str(next_row["batch_id"]),
            "recommended_next_task_type": str(next_row["task_type"]),
            "recommended_next_site_id": str(next_row["site_id"]),
        }
    queue_paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {queue_paths.queue_csv}")
    print(f"Wrote {queue_paths.summary_json}")
    print(f"Pending tasks: {summary['n_pending_tasks']}")
    if summary["n_pending_tasks"]:
        print(
            f"Next batch: {summary['recommended_next_batch']} "
            f"({summary['recommended_next_task_type']}, {summary['recommended_next_site_id']})"
        )


if __name__ == "__main__":
    app()
