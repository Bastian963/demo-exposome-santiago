#!/usr/bin/env python3
"""Run a bounded, sequential, resumable cohort-priority city queue.

This is a human-launched supervisor.  It delegates every provider call to the
canonical ``run_multicity_overnight.py`` runner, which owns the scientific
checkpoints, retries and per-task logs.  The small state file below ``cache/``
only remembers which city completed a full pipeline so a week-long session
does not repeat completed publication work.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.multicity_overnight import (  # noqa: E402
    RunLock,
    load_batch_config,
    select_cities,
    validate_batch_studies,
)


DEFAULT_CONFIG = Path("config/operations/cohort_latam_ready.yaml")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_state(path: Path, *, config: Path, digest: str, city_ids: list[str], reset: bool) -> dict[str, Any]:
    if reset or not path.exists():
        return {
            "schema_version": 1,
            "config": str(config.relative_to(REPO_ROOT)),
            "config_sha256": digest,
            "started_utc": _utc_now(),
            "finished_utc": None,
            "cities": {city_id: {"status": "pending", "failure_cycles": 0, "runs": []} for city_id in city_ids},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported weekly state schema in {path}")
    if payload.get("config_sha256") != digest:
        raise ValueError(
            "The queue configuration changed since this state was created. "
            "Review the completed cities, then restart explicitly with --reset-state."
        )
    states = payload.get("cities")
    if not isinstance(states, dict):
        raise ValueError(f"Invalid city state in {path}")
    for city_id in city_ids:
        states.setdefault(city_id, {"status": "pending", "failure_cycles": 0, "runs": []})
    return payload


def _latest_run_for_city(started_at: float, city_id: str) -> Path | None:
    root = REPO_ROOT / "cache" / "multicity_runs"
    if not root.exists():
        return None
    candidates: list[Path] = []
    for run_dir in root.iterdir():
        summary = run_dir / "summary.json"
        if not summary.is_file() or summary.stat().st_mtime < started_at - 2:
            continue
        try:
            payload = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if any(task.get("city_id") == city_id for task in payload.get("tasks", [])):
            candidates.append(run_dir)
    return max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None


def _counts_for(run_dir: Path | None) -> dict[str, int]:
    if run_dir is None:
        return {"interrupted": 1}
    payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    raw_counts = payload.get("counts", {})
    return {str(key): int(value) for key, value in raw_counts.items()}


def _classify(counts: dict[str, int], failure_cycles: int, max_failure_cycles: int) -> tuple[str, int]:
    if not any(counts.values()):
        return "needs_review", failure_cycles + 1
    if counts.get("failed", 0) or counts.get("blocked", 0) or counts.get("interrupted", 0):
        next_cycles = failure_cycles + 1
        return ("needs_review" if next_cycles >= max_failure_cycles else "pending"), next_cycles
    if counts.get("deferred", 0):
        return "pending", failure_cycles
    return "completed", failure_cycles


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--city", action="append", help="City id or aggregate study; repeatable.")
    parser.add_argument("--duration-hours", type=float, default=168.0)
    parser.add_argument("--slice-hours", type=float, default=10.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--retry-wait-minutes", type=float, default=10.0)
    parser.add_argument("--between-slices-minutes", type=float, default=5.0)
    parser.add_argument("--max-failure-cycles", type=int, default=3)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--reset-state", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the queue without writing or contacting providers.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.duration_hours <= 0 or args.slice_hours <= 0:
        raise ValueError("duration-hours and slice-hours must be positive")
    if args.max_failure_cycles < 1:
        raise ValueError("max-failure-cycles must be at least 1")
    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    batch = load_batch_config(config_path, repo_root=REPO_ROOT)
    chosen = select_cities(batch, args.city)
    chosen_ids = [city.id for city in chosen]
    validate_batch_studies(type(batch)(batch.path, batch.portable_layers, chosen), repo_root=REPO_ROOT)
    digest = _config_digest(batch.path)

    if args.dry_run:
        print("Validated cohort LatAm queue:")
        for city in chosen:
            print(f"- {city.id}: {city.aggregate_study} + {city.native_study}")
        print("Each slice delegates to:")
        print(
            f"  {sys.executable} scripts/run_multicity_overnight.py --config "
            f"{batch.path.relative_to(REPO_ROOT)} --city <city> --max-hours {args.slice_hours:g}"
        )
        return 0

    state_path = args.state or REPO_ROOT / "cache" / "cohort_latam_week" / f"{batch.path.stem}.json"
    if not state_path.is_absolute():
        state_path = REPO_ROOT / state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state(
        state_path,
        config=batch.path,
        digest=digest,
        city_ids=chosen_ids,
        reset=args.reset_state,
    )
    deadline = time.monotonic() + args.duration_hours * 3600
    runner = REPO_ROOT / "scripts" / "run_multicity_overnight.py"

    with RunLock(REPO_ROOT / "cache" / ".cohort_latam_week.lock"):
        while time.monotonic() < deadline:
            pending = [city_id for city_id in chosen_ids if state["cities"][city_id]["status"] == "pending"]
            if not pending:
                break
            for city_id in pending:
                if time.monotonic() >= deadline:
                    break
                command = [
                    sys.executable,
                    str(runner),
                    "--config",
                    str(batch.path.relative_to(REPO_ROOT)),
                    "--city",
                    city_id,
                    "--max-hours",
                    str(args.slice_hours),
                    "--attempts",
                    str(args.attempts),
                    "--retry-wait-minutes",
                    str(args.retry_wait_minutes),
                ]
                print(f"\n=== weekly slice: {city_id} at {_utc_now()} ===")
                started_at = time.time()
                completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
                run_dir = _latest_run_for_city(started_at, city_id)
                counts = _counts_for(run_dir)
                record = state["cities"][city_id]
                status, failure_cycles = _classify(
                    counts,
                    int(record.get("failure_cycles", 0)),
                    args.max_failure_cycles,
                )
                record["status"] = status
                record["failure_cycles"] = failure_cycles
                record.setdefault("runs", []).append(
                    {
                        "finished_utc": _utc_now(),
                        "returncode": completed.returncode,
                        "run_dir": str(run_dir.relative_to(REPO_ROOT)) if run_dir else None,
                        "counts": counts,
                    }
                )
                _atomic_json(state_path, state)
                print(f"weekly state {city_id}: {status} ({counts})")
                if status == "pending" and args.between_slices_minutes:
                    time.sleep(args.between_slices_minutes * 60)

    if all(state["cities"][city_id]["status"] == "completed" for city_id in chosen_ids):
        state["finished_utc"] = _utc_now()
        _atomic_json(state_path, state)
        print(f"All selected cities completed. State: {state_path}")
        return 0
    _atomic_json(state_path, state)
    unresolved = [city_id for city_id in chosen_ids if state["cities"][city_id]["status"] != "completed"]
    print(f"Weekly window ended or review is required for: {', '.join(unresolved)}. State: {state_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
