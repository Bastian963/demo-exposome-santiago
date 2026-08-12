#!/usr/bin/env python3
"""Run the portable multi-city pipeline in resumable overnight task slices.

This command is intentionally human-run because its layer, temporal and green
detail phases contact GEE, Open-Meteo and OSM/Overpass.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shlex
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.multicity_overnight import (  # noqa: E402
    ALL_PHASES,
    RunLock,
    build_task_plan,
    config_sha256,
    execute_task_plan,
    load_batch_config,
    select_cities,
    validate_batch_studies,
)


DEFAULT_CONFIG = Path("config/operations/multicity_14.yaml")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--city",
        action="append",
        help="Batch city id or aggregate Study id; repeatable (default: all).",
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=ALL_PHASES,
        help="Phase to run; repeatable (default: every phase).",
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=10.0,
        help="Stop between task checkpoints after this many hours; 0 disables the limit.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="Attempts for provider-dependent tasks (default: 2).",
    )
    parser.add_argument(
        "--retry-wait-minutes",
        type=float,
        default=10.0,
        help="Wait between provider retries (default: 10 minutes).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the exact task plan without writing or contacting providers.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        batch = load_batch_config(args.config, repo_root=REPO_ROOT)
        selected = select_cities(batch, args.city)
        selected_batch = type(batch)(batch.path, batch.portable_layers, selected)
        validate_batch_studies(selected_batch, repo_root=REPO_ROOT)
        phases = tuple(args.phase or ALL_PHASES)
        tasks = build_task_plan(
            selected_batch,
            repo_root=REPO_ROOT,
            cities=selected,
            phases=phases,
        )
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "config": str(batch.path.relative_to(REPO_ROOT)),
                "config_sha256": config_sha256(batch.path),
                "cities": [city.id for city in selected],
                "phases": list(phases),
                "portable_layers": len(batch.portable_layers),
                "tasks": len(tasks),
                "max_hours": None if args.max_hours == 0 else args.max_hours,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.dry_run:
        for task in tasks:
            print(f"[{task.city_id}/{task.phase}] {task.label}")
            print(f"  {shlex.join(task.command)}")
        return 0

    if not (REPO_ROOT / ".venv/bin/python").is_file():
        print("Missing .venv; run: uv sync --all-extras", file=sys.stderr)
        return 2
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = REPO_ROOT / "cache" / "multicity_runs" / stamp
    try:
        with RunLock(REPO_ROOT / "cache/.multicity_overnight.lock"):
            results = execute_task_plan(
                tasks,
                repo_root=REPO_ROOT,
                run_dir=run_dir,
                max_hours=None if args.max_hours == 0 else args.max_hours,
                attempts=args.attempts,
                retry_wait_minutes=args.retry_wait_minutes,
            )
    except KeyboardInterrupt:
        print(f"Interrupted safely. Resume with the same command. State: {run_dir}")
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Run error: {exc}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"\nRun state: {run_dir}")
    print(json.dumps(counts, sort_keys=True))
    if counts.get("failed") or counts.get("blocked"):
        print("Review summary.md and incident_candidates.md, then rerun the same command.")
        return 1
    if counts.get("deferred"):
        print("Time budget reached cleanly; rerun the same command for the next checkpoint slice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
