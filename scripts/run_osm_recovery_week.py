#!/usr/bin/env python3
"""Recover pending OSM layers without repeatedly hammering Overpass.

The command is human-launched.  It runs only the portable OSM layers with
``--resume`` and serializes cities, so finished scientific checkpoints are
never repeated.  A failed layer waits for the configured interval before the
next pass; after a bounded number of failures it is marked for review.  Once a
city's OSM tasks all succeed, the canonical multicity runner completes its
temporal, detail, staging, audit and publication phases.
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

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.multicity_overnight import RunLock  # noqa: E402


DEFAULT_CONFIG = Path("config/operations/osm_recovery_colombia.yaml")
POST_PHASES = ("temporal", "resolution", "publish", "validate")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


def _safe_slug(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in text):
        raise ValueError(f"{label} must be a lowercase slug: {value!r}")
    return text


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported recovery config schema in {path}")
    layers = payload.get("osm_layers")
    if not isinstance(layers, list) or not layers or not all(isinstance(item, str) for item in layers):
        raise ValueError("osm_layers must be a non-empty list")
    if len(layers) != len(set(layers)):
        raise ValueError("osm_layers must not contain duplicates")
    cities = payload.get("cities")
    if not isinstance(cities, list) or not cities:
        raise ValueError("cities must be a non-empty list")
    for city in cities:
        if not isinstance(city, dict):
            raise ValueError("every city must be a mapping")
        for field in ("id", "aggregate_study", "native_study"):
            _safe_slug(city.get(field), field)
    if len({_safe_slug(city["id"], "id") for city in cities}) != len(cities):
        raise ValueError("city ids must be unique")
    batch_config = payload.get("batch_config")
    if not isinstance(batch_config, str) or not batch_config:
        raise ValueError("batch_config must be a non-empty path")
    return payload


def _new_state(config: Path, city_ids: list[str], layers: list[str], digest: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "config": str(config.relative_to(REPO_ROOT)),
        "config_sha256": digest,
        "started_utc": _utc_now(),
        "finished_utc": None,
        "cities": {
            city_id: {
                "status": "pending",
                "post_status": "pending",
                "tasks": {
                    f"{scope}:{layer}": {
                        "status": "pending",
                        "failure_cycles": 0,
                        "attempts": [],
                    }
                    for scope in ("aggregate", "native")
                    for layer in layers
                },
                "post_attempts": [],
            }
            for city_id in city_ids
        },
    }


def _load_state(path: Path, *, config: Path, city_ids: list[str], layers: list[str], reset: bool) -> dict[str, Any]:
    digest = sha256(config.read_bytes()).hexdigest()
    if reset or not path.exists():
        return _new_state(config, city_ids, layers, digest)
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError(f"Unsupported state schema in {path}")
    if state.get("config_sha256") != digest:
        raise ValueError("Recovery configuration changed; review state, then use --reset-state.")
    if not isinstance(state.get("cities"), dict):
        raise ValueError(f"Invalid city state in {path}")
    return state


def _run(command: list[str], *, log_path: Path) -> int:
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {_utc_now()} ===\n$ {' '.join(command)}\n")
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        return process.wait()


def _task_status(returncode: int, failure_cycles: int, max_failure_cycles: int) -> tuple[str, int]:
    if returncode == 0:
        return "completed", failure_cycles
    next_cycles = failure_cycles + 1
    return ("needs_review" if next_cycles >= max_failure_cycles else "pending"), next_cycles


def _latest_multicity_counts(started_at: float, city_id: str) -> dict[str, int] | None:
    runs_root = REPO_ROOT / "cache" / "multicity_runs"
    if not runs_root.exists():
        return None
    candidates: list[Path] = []
    for run_dir in runs_root.iterdir():
        summary = run_dir / "summary.json"
        if not summary.is_file() or summary.stat().st_mtime < started_at - 2:
            continue
        try:
            payload = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if any(task.get("city_id") == city_id for task in payload.get("tasks", [])):
            candidates.append(summary)
    if not candidates:
        return None
    payload = json.loads(max(candidates, key=lambda item: item.stat().st_mtime).read_text(encoding="utf-8"))
    return {str(key): int(value) for key, value in payload.get("counts", {}).items()}


def _post_status(returncode: int, counts: dict[str, int] | None) -> str:
    if returncode != 0 or counts is None:
        return "needs_review"
    if counts.get("failed", 0) or counts.get("blocked", 0) or counts.get("interrupted", 0):
        return "needs_review"
    if counts.get("deferred", 0):
        return "pending"
    return "completed"


def _city_osm_complete(city_state: dict[str, Any]) -> bool:
    return all(task["status"] == "completed" for task in city_state["tasks"].values())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--city", action="append", help="City id; repeatable (default: all).")
    parser.add_argument("--duration-hours", type=float, default=168.0)
    parser.add_argument("--retry-interval-hours", type=float)
    parser.add_argument("--max-failure-cycles", type=int)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--reset-state", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    config = _load_config(config_path)
    retry_hours = args.retry_interval_hours or float(config.get("retry_interval_hours", 6))
    max_failures = args.max_failure_cycles or int(config.get("max_failure_cycles", 3))
    if args.duration_hours <= 0 or retry_hours <= 0 or max_failures < 1:
        raise ValueError("duration/retry intervals must be positive and max failures at least one")
    requested = set(args.city or ())
    cities = [city for city in config["cities"] if not requested or city["id"] in requested]
    unknown = requested - {city["id"] for city in config["cities"]}
    if unknown:
        raise ValueError(f"Unknown recovery cities: {sorted(unknown)}")
    city_ids = [city["id"] for city in cities]
    layers = list(config["osm_layers"])

    if args.dry_run:
        print(f"OSM recovery queue: {', '.join(city_ids)}")
        print(f"Layers: {', '.join(layers)}")
        print(f"Retry interval: {retry_hours:g} h; max failure cycles: {max_failures}")
        for city in cities:
            for study in (city["aggregate_study"], city["native_study"]):
                print(f"  .venv/bin/exposome run --study {study} --layers <osm-layer> --resume --no-build-master")
        return 0

    state_path = args.state or REPO_ROOT / "cache" / "osm_recovery_week" / f"{config_path.stem}.json"
    if not state_path.is_absolute():
        state_path = REPO_ROOT / state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    logs_dir = state_path.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    state = _load_state(state_path, config=config_path, city_ids=city_ids, layers=layers, reset=args.reset_state)
    deadline = time.monotonic() + args.duration_hours * 3600
    exposome = str(REPO_ROOT / ".venv" / "bin" / "exposome")
    runner = str(REPO_ROOT / "scripts" / "run_multicity_overnight.py")

    with RunLock(REPO_ROOT / "cache" / ".osm_recovery_week.lock"):
        while time.monotonic() < deadline:
            any_pending = False
            for city in cities:
                city_state = state["cities"][city["id"]]
                if city_state["status"] == "needs_review":
                    continue
                for scope, study in (("aggregate", city["aggregate_study"]), ("native", city["native_study"])):
                    for layer in layers:
                        task_key = f"{scope}:{layer}"
                        task = city_state["tasks"][task_key]
                        if task["status"] != "pending":
                            continue
                        any_pending = True
                        command = [exposome, "run", "--study", study, "--layers", layer, "--resume", "--no-build-master"]
                        log_path = logs_dir / f"{city['id']}__{scope}__{layer}.log"
                        print(f"\n=== OSM recovery: {city['id']} / {scope} / {layer} ===")
                        returncode = _run(command, log_path=log_path)
                        status, failures = _task_status(returncode, int(task["failure_cycles"]), max_failures)
                        task["status"] = status
                        task["failure_cycles"] = failures
                        task["attempts"].append({"finished_utc": _utc_now(), "returncode": returncode, "log": str(log_path.relative_to(REPO_ROOT))})
                        _atomic_json(state_path, state)

                if any(task["status"] == "needs_review" for task in city_state["tasks"].values()):
                    city_state["status"] = "needs_review"
                    _atomic_json(state_path, state)
                    continue
                if not _city_osm_complete(city_state) or city_state["post_status"] == "completed":
                    continue

                print(f"\n=== publication pipeline: {city['id']} ===")
                post_log = logs_dir / f"{city['id']}__publication.log"
                command = [sys.executable, runner, "--config", config["batch_config"], "--city", city["id"]]
                for phase in POST_PHASES:
                    command.extend(("--phase", phase))
                command.extend(("--max-hours", "10"))
                started_at = time.time()
                returncode = _run(command, log_path=post_log)
                counts = _latest_multicity_counts(started_at, city["id"])
                post_status = _post_status(returncode, counts)
                city_state["post_attempts"].append(
                    {
                        "finished_utc": _utc_now(),
                        "returncode": returncode,
                        "counts": counts,
                        "log": str(post_log.relative_to(REPO_ROOT)),
                    }
                )
                city_state["post_status"] = post_status
                city_state["status"] = post_status
                any_pending = any_pending or post_status == "pending"
                _atomic_json(state_path, state)

            if not any_pending:
                break
            if time.monotonic() + retry_hours * 3600 >= deadline:
                break
            print(f"\nOSM pass complete; waiting {retry_hours:g} hours before resuming pending tasks.")
            time.sleep(retry_hours * 3600)

    if all(state["cities"][city_id]["status"] == "completed" for city_id in city_ids):
        state["finished_utc"] = _utc_now()
        _atomic_json(state_path, state)
        print(f"All OSM recovery cities completed. State: {state_path}")
        return 0
    _atomic_json(state_path, state)
    unresolved = [city_id for city_id in city_ids if state["cities"][city_id]["status"] != "completed"]
    print(f"Recovery window ended or review is required for: {', '.join(unresolved)}. State: {state_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
