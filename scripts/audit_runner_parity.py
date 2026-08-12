"""Audit explicit gates before retiring any legacy Layer script."""
from __future__ import annotations

from pathlib import Path
import sys

import typer


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.runner_parity import load_runner_parity  # noqa: E402


def main() -> None:
    records = load_runner_parity()
    ready = [record.layer_id for record in records if record.retirement_ready]
    adapters = [record.layer_id for record in records if record.state == "adapter"]
    typer.echo(f"registered={sum(record.registered for record in records)}/{len(records)}")
    typer.echo(f"legacy_adapters={len(adapters)}")
    typer.echo("retirement_ready=" + (",".join(ready) if ready else "none"))


if __name__ == "__main__":
    typer.run(main)
