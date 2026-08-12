"""Collect ECOSTRESS land surface temperature for a study.

LONG-RUNNING: this hits NASA Earthdata and streams hundreds of granules per
month.  Per CLAUDE.md it is never executed by an agent -- hand the command to a
human for an overnight run.  It checkpoints per granule and resumes.

Volume, measured rather than assumed: ``santiago_communes`` spans 180 x 151 km
(the whole Region Metropolitana) = ~12 MGRS tiles across UTM zones 18 and 19,
and CMR reports ~400 granules per month over that footprint.  Granules are
therefore streamed and folded into study-grid accumulators, never stored.
Start with ``--start/--end`` on one season to calibrate wall time before
committing to the full 2019-present record.

The work itself lives in :mod:`exposome.climate.ecostress_layer` so the layer
has an importable in-process runner; this file is only the CLI.

Prerequisites
-------------
    uv sync --all-extras       # earthaccess is a new dependency

    # earthaccess ships NO command-line tool -- there is no `earthaccess login`.
    # Authenticate once (prompts, then persists to ~/.netrc):
    .venv/bin/python -c \
        "import earthaccess; earthaccess.login(strategy='interactive', persist=True)"

Needs a free Earthdata Login account: https://urs.earthdata.nasa.gov
``EARTHDATA_USERNAME``/``EARTHDATA_PASSWORD`` or ``EARTHDATA_TOKEN`` work too.

``--dry-run`` still queries NASA CMR, so it needs both of the above; it skips
the downloads, not the search.

Typical use
-----------
    python scripts/run_climate_lst_ecostress.py \
        --study santiago_communes --start 2023-01-01 --end 2023-03-01 --dry-run
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.climate.ecostress_layer import (  # noqa: E402
    LAYER_ID,
    build_climate_lst_ecostress_layer,
)
from exposome.studies import load_study  # noqa: E402

app = typer.Typer(help="Collect ECOSTRESS 70 m LST for a study.")


@app.command()
def run(
    study: str = typer.Option(..., "--study"),
    # ECOSTRESS launched in July 2018, so 2019 is the first complete year.
    # Defaults come from config/layers/climate_lst_ecostress.yaml when omitted.
    start: str | None = typer.Option(None, "--start", help="ISO date, inclusive"),
    end: str | None = typer.Option(None, "--end", help="ISO date, exclusive"),
    version: str | None = typer.Option(None, "--version"),
    max_qc_level: int | None = typer.Option(
        None, "--max-qc-level", help="0=best, 1=nominal"
    ),
    checkpoint_interval: int = typer.Option(25, "--checkpoint-interval"),
    cache_dir: Path | None = typer.Option(None, "--cache-dir"),
    out_dir: Path | None = typer.Option(None, "--out-dir"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Search CMR and report counts; download nothing"
    ),
) -> None:
    context = load_study(study)
    build_climate_lst_ecostress_layer(
        study,
        cache_dir=cache_dir or Path(context.paths.layer_cache(LAYER_ID)),
        out_dir=out_dir or Path(context.paths.layer_processed(LAYER_ID)),
        start=start,
        end=end,
        version=version,
        max_qc_level=max_qc_level,
        checkpoint_interval=checkpoint_interval,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    app()
