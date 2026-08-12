"""Checkpoint-aware orchestration for human-run multi-city collection.

The orchestrator does not implement provider access. It composes the canonical
Study, temporal, spatial-detail and publication commands into small restartable
tasks. Raw logs and incident candidates live below ``cache/`` and are therefore
local operation state, not reviewed project documentation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
from typing import Iterable, Mapping, Sequence, TextIO

import yaml

from .releases import canonical_enabled_layers
from .studies import load_study
from .temporal_exposomes import discover_temporal_specs


ALL_PHASES = ("layers", "temporal", "resolution", "publish", "validate")


@dataclass(frozen=True)
class BatchCity:
    id: str
    aggregate_study: str
    native_study: str
    portable_layers: tuple[str, ...] | None = None


@dataclass(frozen=True)
class BatchConfig:
    path: Path
    portable_layers: tuple[str, ...]
    cities: tuple[BatchCity, ...]


@dataclass(frozen=True)
class BatchTask:
    key: str
    city_id: str
    phase: str
    label: str
    command: tuple[str, ...]
    requires: tuple[str, ...] = ()
    retryable: bool = False


@dataclass
class TaskResult:
    key: str
    city_id: str
    phase: str
    label: str
    command: list[str]
    status: str
    attempts: int = 0
    returncode: int | None = None
    started_utc: str | None = None
    finished_utc: str | None = None
    duration_seconds: float = 0.0
    log: str | None = None
    reason: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in text):
        raise ValueError(f"{label} must be a lowercase slug: {value!r}")
    return text


def load_batch_config(path: str | Path, *, repo_root: str | Path) -> BatchConfig:
    """Load and validate the declarative city/study batch."""
    root = Path(repo_root).resolve()
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = root / config_path
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported batch schema_version in {config_path}")
    raw_layers = payload.get("portable_layers")
    if not isinstance(raw_layers, list) or not all(isinstance(item, str) for item in raw_layers):
        raise ValueError("portable_layers must be a list of layer ids")
    portable_layers = tuple(raw_layers)
    if len(portable_layers) != 14 or len(set(portable_layers)) != 14:
        raise ValueError("portable_layers must contain exactly 14 unique layer ids")
    raw_cities = payload.get("cities")
    if not isinstance(raw_cities, list) or not raw_cities:
        raise ValueError("cities must be a non-empty list")
    cities: list[BatchCity] = []
    for record in raw_cities:
        if not isinstance(record, Mapping):
            raise ValueError("Every city batch entry must be a mapping")
        raw_city_layers = record.get("portable_layers")
        if raw_city_layers is not None and (
            not isinstance(raw_city_layers, list)
            or not all(isinstance(item, str) for item in raw_city_layers)
            or len(set(raw_city_layers)) != len(raw_city_layers)
            or not set(raw_city_layers).issubset(set(portable_layers))
        ):
            raise ValueError(
                "city portable_layers must be a unique subset of global portable_layers"
            )
        cities.append(
            BatchCity(
                id=_safe_id(record.get("id"), "city id"),
                aggregate_study=_safe_id(record.get("aggregate_study"), "aggregate study"),
                native_study=_safe_id(record.get("native_study"), "native study"),
                portable_layers=(
                    tuple(raw_city_layers) if raw_city_layers is not None else None
                ),
            )
        )
    if len({city.id for city in cities}) != len(cities):
        raise ValueError("Batch city ids must be unique")
    return BatchConfig(config_path.resolve(), portable_layers, tuple(cities))


def validate_batch_studies(batch: BatchConfig, *, repo_root: str | Path) -> None:
    """Prove that every pair targets one location and contains the portable 14."""
    root = Path(repo_root).resolve()
    for city in batch.cities:
        expected = set(city.portable_layers or batch.portable_layers)
        aggregate = load_study(city.aggregate_study, repo_root_path=root)
        native = load_study(city.native_study, repo_root_path=root)
        if aggregate.is_native:
            raise ValueError(f"{city.aggregate_study} must be aggregate")
        if not native.is_native:
            raise ValueError(f"{city.native_study} must be native")
        if aggregate.location.id != native.location.id:
            raise ValueError(
                f"{city.id} study pair uses different locations: "
                f"{aggregate.location.id} vs {native.location.id}"
            )
        declared_native = (aggregate.study.raw.get("detail") or {}).get("native_study")
        if declared_native != city.native_study:
            raise ValueError(
                f"{city.aggregate_study} declares detail.native_study={declared_native!r}, "
                f"expected {city.native_study!r}"
            )
        for context, label in ((aggregate, "aggregate"), (native, "native")):
            enabled = set(canonical_enabled_layers(context))
            missing = sorted(expected - enabled)
            if missing:
                raise ValueError(f"{city.id} {label} study lacks portable layers: {missing}")


def select_cities(batch: BatchConfig, selected: Iterable[str] | None) -> tuple[BatchCity, ...]:
    requested = tuple(selected or ())
    if not requested:
        return batch.cities
    by_id = {city.id: city for city in batch.cities}
    by_study = {city.aggregate_study: city for city in batch.cities}
    resolved: list[BatchCity] = []
    for value in requested:
        city = by_id.get(value) or by_study.get(value)
        if city is None:
            raise ValueError(f"Unknown batch city/study {value!r}")
        if city not in resolved:
            resolved.append(city)
    return tuple(resolved)


def build_task_plan(
    batch: BatchConfig,
    *,
    repo_root: str | Path,
    cities: Sequence[BatchCity] | None = None,
    phases: Iterable[str] = ALL_PHASES,
) -> tuple[BatchTask, ...]:
    """Build small task waves so a time budget stops between durable checkpoints."""
    root = Path(repo_root).resolve()
    chosen = tuple(cities or batch.cities)
    selected_phases = set(phases)
    unknown = sorted(selected_phases - set(ALL_PHASES))
    if unknown:
        raise ValueError(f"Unknown phases: {unknown}")
    python = str(root / ".venv" / "bin" / "python")
    exposome = str(root / ".venv" / "bin" / "exposome")
    tasks: list[BatchTask] = []

    def add(
        key: str,
        city: BatchCity,
        phase: str,
        label: str,
        command: Sequence[str],
        *,
        requires: Sequence[str] = (),
        retryable: bool = False,
    ) -> None:
        tasks.append(
            BatchTask(
                key=key,
                city_id=city.id,
                phase=phase,
                label=label,
                command=tuple(map(str, command)),
                requires=tuple(requires),
                retryable=retryable,
            )
        )

    # Offline preflight is always first. It catches a broken study before any
    # provider call and is cheap on every resumed night.
    for city in chosen:
        add(
            f"{city.id}:preflight:aggregate",
            city,
            "preflight",
            f"preflight {city.aggregate_study}",
            (exposome, "run", "--study", city.aggregate_study, "--dry-run"),
        )
        add(
            f"{city.id}:preflight:native",
            city,
            "preflight",
            f"preflight {city.native_study}",
            (exposome, "run", "--study", city.native_study, "--dry-run"),
        )

    aggregate_keys: dict[str, list[str]] = {city.id: [] for city in chosen}
    native_keys: dict[str, list[str]] = {city.id: [] for city in chosen}
    if "layers" in selected_phases:
        # One subprocess per layer means a permanent failure does not prevent
        # independent layers/cities from checkpointing useful work.
        for city in chosen:
            for layer_id in city.portable_layers or batch.portable_layers:
                key = f"{city.id}:aggregate:{layer_id}"
                aggregate_keys[city.id].append(key)
                add(
                    key,
                    city,
                    "layers",
                    f"{city.aggregate_study} / {layer_id}",
                    (
                        exposome,
                        "run",
                        "--study",
                        city.aggregate_study,
                        "--layers",
                        layer_id,
                        "--resume",
                        "--no-build-master",
                    ),
                    requires=(f"{city.id}:preflight:aggregate",),
                    retryable=True,
                )
        for city in chosen:
            for layer_id in city.portable_layers or batch.portable_layers:
                key = f"{city.id}:native:{layer_id}"
                native_keys[city.id].append(key)
                add(
                    key,
                    city,
                    "layers",
                    f"{city.native_study} / {layer_id}",
                    (
                        exposome,
                        "run",
                        "--study",
                        city.native_study,
                        "--layers",
                        layer_id,
                        "--resume",
                        "--no-build-master",
                    ),
                    requires=(f"{city.id}:preflight:native",),
                    retryable=True,
                )
        for city in chosen:
            add(
                f"{city.id}:layers:materialize-base",
                city,
                "layers",
                f"materialize base {city.aggregate_study}",
                (exposome, "materialize", "--study", city.aggregate_study),
                requires=aggregate_keys[city.id],
            )
            add(
                f"{city.id}:layers:seal-native",
                city,
                "layers",
                f"seal native release {city.native_study}",
                (exposome, "run", "--study", city.native_study, "--resume"),
                requires=native_keys[city.id],
            )

    temporal_keys: dict[str, list[str]] = {city.id: [] for city in chosen}
    if "temporal" in selected_phases:
        for city in chosen:
            context = load_study(city.aggregate_study, repo_root_path=root)
            for spec in discover_temporal_specs(context):
                key = f"{city.id}:temporal:{spec.layer_id}"
                temporal_keys[city.id].append(key)
                add(
                    key,
                    city,
                    "temporal",
                    f"annual {city.aggregate_study} / {spec.layer_id}",
                    (
                        python,
                        "scripts/run_missing_annual_exposomes.py",
                        "--study",
                        city.aggregate_study,
                        "--layer",
                        spec.layer_id,
                        "--resume",
                    ),
                    requires=(f"{city.id}:preflight:aggregate",),
                    retryable=True,
                )

    resolution_keys: dict[str, list[str]] = {city.id: [] for city in chosen}
    if "resolution" in selected_phases:
        for city in chosen:
            detail_key = f"{city.id}:resolution:detail"
            resolution_keys[city.id].append(detail_key)
            add(
                detail_key,
                city,
                "resolution",
                f"verified detail {city.aggregate_study}",
                (exposome, "detail", "--study", city.aggregate_study, "--resume"),
                requires=(f"{city.id}:layers:seal-native",),
            )
            enabled = set(
                canonical_enabled_layers(
                    load_study(city.aggregate_study, repo_root_path=root)
                )
            )
            if "greenspace_multisource" in enabled:
                green_key = f"{city.id}:resolution:green"
                resolution_keys[city.id].append(green_key)
                add(
                    green_key,
                    city,
                    "resolution",
                    f"Dynamic World grid {city.aggregate_study}",
                    (
                        python,
                        "scripts/export_webapp_green_subcomuna.py",
                        "--study",
                        city.aggregate_study,
                    ),
                    requires=(f"{city.id}:aggregate:greenspace_multisource",),
                    retryable=True,
                )

    publish_keys: dict[str, str] = {}
    if "publish" in selected_phases:
        for city in chosen:
            temporal_gate_key = f"{city.id}:publish:temporal-gate"
            profile_key = f"{city.id}:publish:profiles"
            final_key = f"{city.id}:publish:materialize-final"
            verify_key = f"{city.id}:publish:verify"
            preview_key = f"{city.id}:publish:preview"
            preview_audit_key = f"{city.id}:publish:preview-audit"
            preview_coverage_key = f"{city.id}:publish:preview-production"
            publish_key = f"{city.id}:publish:webapp"
            publish_keys[city.id] = publish_key
            preview_root = root / "cache/multicity_publish_gate" / city.id
            context = load_study(city.aggregate_study, repo_root_path=root)
            preview_bundle = (
                preview_root
                / "v1"
                / context.location.country_code.lower()
                / context.city
                / context.study.id
            )
            add(
                temporal_gate_key,
                city,
                "publish",
                f"temporal completeness {city.aggregate_study}",
                (
                    python,
                    "scripts/run_missing_annual_exposomes.py",
                    "--study",
                    city.aggregate_study,
                    "--status",
                    "--require-complete",
                ),
                requires=temporal_keys[city.id],
            )
            add(
                profile_key,
                city,
                "publish",
                f"profiles {city.aggregate_study}",
                (python, "scripts/export_study_profiles.py", "--study", city.aggregate_study),
                requires=(f"{city.id}:layers:materialize-base", temporal_gate_key),
            )
            add(
                final_key,
                city,
                "publish",
                f"final release {city.aggregate_study}",
                (exposome, "materialize", "--study", city.aggregate_study),
                requires=(profile_key, *resolution_keys[city.id]),
            )
            add(
                verify_key,
                city,
                "publish",
                f"verify {city.aggregate_study}",
                (exposome, "verify", "--study", city.aggregate_study),
                requires=(final_key,),
            )
            add(
                preview_key,
                city,
                "publish",
                f"staged publication {city.aggregate_study}",
                (
                    exposome,
                    "publish",
                    "--study",
                    city.aggregate_study,
                    "--output",
                    str(preview_root),
                ),
                requires=(verify_key,),
            )
            add(
                preview_audit_key,
                city,
                "publish",
                f"staged strict audit {city.aggregate_study}",
                (exposome, "spatial-audit", "--bundle", str(preview_bundle), "--strict"),
                requires=(preview_key,),
            )
            add(
                preview_coverage_key,
                city,
                "publish",
                f"staged production coverage {city.aggregate_study}",
                (
                    exposome,
                    "resolution-coverage",
                    "--bundle",
                    str(preview_bundle),
                    "--tier",
                    "production",
                ),
                requires=(preview_key,),
            )
            add(
                publish_key,
                city,
                "publish",
                f"publish {city.aggregate_study}",
                (exposome, "publish", "--study", city.aggregate_study),
                requires=(preview_audit_key, preview_coverage_key),
            )

    if "validate" in selected_phases:
        for city in chosen:
            context = load_study(city.aggregate_study, repo_root_path=root)
            bundle = (
                root
                / "webapp/public/data/v1"
                / context.location.country_code.lower()
                / context.city
                / context.study.id
            )
            publish_requirement = (publish_keys[city.id],) if city.id in publish_keys else ()
            add(
                f"{city.id}:validate:spatial-audit",
                city,
                "validate",
                f"strict spatial audit {city.aggregate_study}",
                (exposome, "spatial-audit", "--bundle", str(bundle), "--strict"),
                requires=publish_requirement,
            )
            add(
                f"{city.id}:validate:production",
                city,
                "validate",
                f"production coverage {city.aggregate_study}",
                (
                    exposome,
                    "resolution-coverage",
                    "--bundle",
                    str(bundle),
                    "--tier",
                    "production",
                ),
                requires=publish_requirement,
            )
    keys = [task.key for task in tasks]
    if len(keys) != len(set(keys)):
        raise ValueError("Generated task plan contains duplicate keys")
    return tuple(tasks)


class RunLock:
    """Advisory single-run lock without deleting potentially live state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: TextIO | None = None

    def __enter__(self) -> "RunLock":
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another multicity run holds {self.path}") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()} started={_utc_now()}\n")
        self.handle.flush()
        return self

    def __exit__(self, *_: object) -> None:
        if self.handle is None:
            return
        import fcntl

        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _task_log_name(task: BatchTask) -> str:
    safe = task.key.replace(":", "__").replace("/", "_")
    return f"{safe}.log"


def _run_command(command: Sequence[str], *, cwd: Path, log_path: Path) -> int:
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
            return process.wait()
        except KeyboardInterrupt:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
            raise
        finally:
            process.stdout.close()


def _write_reports(
    run_dir: Path,
    *,
    results: Sequence[TaskResult],
    started_utc: str,
    finished_utc: str | None = None,
) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    payload = {
        "schema_version": 1,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "counts": counts,
        "tasks": [asdict(result) for result in results],
    }
    _atomic_json(run_dir / "summary.json", payload)
    lines = [
        "# Multicity run summary",
        "",
        f"- Started: `{started_utc}`",
        f"- Finished: `{finished_utc or 'running'}`",
        f"- Counts: `{json.dumps(counts, sort_keys=True)}`",
        "",
        "| City | Phase | Task | Status | Attempts | Log |",
        "|---|---|---|---|---:|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.city_id} | {result.phase} | {result.label} | "
            f"{result.status} | {result.attempts} | {result.log or '-'} |"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    failures = [result for result in results if result.status == "failed"]
    incident_lines = [
        "# Incident candidates",
        "",
        "This local file is unreviewed. Inspect the referenced logs, remove sensitive data,",
        "identify the root cause, then promote only the stable lesson to the repository runbook.",
        "",
    ]
    for result in failures:
        incident_lines.extend(
            [
                f"## {result.city_id}: {result.label}",
                "",
                f"- Command: `{shlex.join(result.command)}`",
                f"- Return code: `{result.returncode}`",
                f"- Attempts: `{result.attempts}`",
                f"- Log: `{result.log}`",
                "- Root cause: pending review",
                "- Reusable prevention: pending review",
                "",
            ]
        )
    (run_dir / "incident_candidates.md").write_text(
        "\n".join(incident_lines) + "\n", encoding="utf-8"
    )


def execute_task_plan(
    tasks: Sequence[BatchTask],
    *,
    repo_root: str | Path,
    run_dir: str | Path,
    max_hours: float | None,
    attempts: int,
    retry_wait_minutes: float,
) -> tuple[TaskResult, ...]:
    """Execute a plan sequentially, checkpointing state after every task."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if max_hours is not None and max_hours <= 0:
        raise ValueError("max_hours must be positive")
    root = Path(repo_root).resolve()
    output = Path(run_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "tasks"
    logs.mkdir()
    started_utc = _utc_now()
    started = time.monotonic()
    deadline = None if max_hours is None else started + max_hours * 3600
    results: list[TaskResult] = []
    status_by_key: dict[str, str] = {}
    task_keys = {task.key for task in tasks}
    _write_reports(output, results=results, started_utc=started_utc)

    try:
        for task in tasks:
            if deadline is not None and time.monotonic() >= deadline:
                result = TaskResult(
                    key=task.key,
                    city_id=task.city_id,
                    phase=task.phase,
                    label=task.label,
                    command=list(task.command),
                    status="deferred",
                    reason="overnight time budget reached between checkpoints",
                )
                results.append(result)
                status_by_key[task.key] = result.status
                _write_reports(output, results=results, started_utc=started_utc)
                continue
            failed_requirements = [
                key
                for key in task.requires
                if key in task_keys
                and status_by_key.get(key) in {"failed", "blocked", "interrupted"}
            ]
            deferred_requirements = [
                key
                for key in task.requires
                if key in task_keys and status_by_key.get(key) == "deferred"
            ]
            if failed_requirements or deferred_requirements:
                blocked = bool(failed_requirements)
                requirements = failed_requirements or deferred_requirements
                result = TaskResult(
                    key=task.key,
                    city_id=task.city_id,
                    phase=task.phase,
                    label=task.label,
                    command=list(task.command),
                    status="blocked" if blocked else "deferred",
                    reason=(
                        "requirements failed: " if blocked else "requirements deferred: "
                    )
                    + ", ".join(requirements),
                )
                results.append(result)
                status_by_key[task.key] = result.status
                _write_reports(output, results=results, started_utc=started_utc)
                continue

            log_path = logs / _task_log_name(task)
            result = TaskResult(
                key=task.key,
                city_id=task.city_id,
                phase=task.phase,
                label=task.label,
                command=list(task.command),
                status="running",
                started_utc=_utc_now(),
                log=str(log_path.relative_to(output)),
            )
            results.append(result)
            _write_reports(output, results=results, started_utc=started_utc)
            task_started = time.monotonic()
            allowed_attempts = attempts if task.retryable else 1
            print(f"\n=== {task.city_id} / {task.phase}: {task.label} ===")
            print(f"$ {shlex.join(task.command)}")
            for attempt in range(1, allowed_attempts + 1):
                result.attempts = attempt
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"\n=== attempt {attempt}/{allowed_attempts} at {_utc_now()} ===\n")
                    log.write(f"$ {shlex.join(task.command)}\n")
                try:
                    returncode = _run_command(task.command, cwd=root, log_path=log_path)
                except OSError as exc:
                    returncode = 127
                    with log_path.open("a", encoding="utf-8") as log:
                        log.write(f"launcher error: {type(exc).__name__}: {exc}\n")
                result.returncode = returncode
                if returncode == 0:
                    result.status = "success"
                    break
                if attempt >= allowed_attempts:
                    result.status = "failed"
                    break
                wait_seconds = retry_wait_minutes * 60
                if deadline is not None and time.monotonic() + wait_seconds >= deadline:
                    result.status = "failed"
                    result.reason = "retry omitted because the time budget would expire"
                    break
                print(
                    f"Task failed with {returncode}; retrying in "
                    f"{retry_wait_minutes:g} minutes..."
                )
                time.sleep(wait_seconds)
            result.finished_utc = _utc_now()
            result.duration_seconds = round(time.monotonic() - task_started, 3)
            status_by_key[task.key] = result.status
            _write_reports(output, results=results, started_utc=started_utc)
    except KeyboardInterrupt:
        if results and results[-1].status == "running":
            results[-1].status = "interrupted"
            results[-1].finished_utc = _utc_now()
            status_by_key[results[-1].key] = "interrupted"
        _write_reports(
            output,
            results=results,
            started_utc=started_utc,
            finished_utc=_utc_now(),
        )
        raise
    _write_reports(
        output,
        results=results,
        started_utc=started_utc,
        finished_utc=_utc_now(),
    )
    return tuple(results)


def config_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
