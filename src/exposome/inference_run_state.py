"""Atomic, resumable state for long-running hospitalization inference models."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


STATE_SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset({"ok", "failed_diagnostics"})
SAMPLING_PHASES = frozenset(
    {"primary", "negative-controls", "sensitivities", "commune-loo"}
)


class InferenceStateError(RuntimeError):
    """Raised when saved model state cannot be safely reused."""


class InferenceConfigMismatch(InferenceStateError):
    """Raised when an output directory contains another scientific run."""


@dataclass(frozen=True)
class ModelTask:
    """One deterministic sampling unit in the publication workflow."""

    phase: str
    model_id: str
    outcome: str
    exposure: str
    model_name: str
    variant: str | None = None
    excluded_spatial_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "model_id": self.model_id,
            "outcome": self.outcome,
            "exposure": self.exposure,
            "model_name": self.model_name,
            "variant": self.variant,
            "excluded_spatial_id": self.excluded_spatial_id,
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scientific_fingerprint(
    config: Mapping[str, Any],
    input_hashes: Mapping[str, str],
) -> str:
    """Hash scientific settings and materialized inputs, excluding runtime paths."""
    payload = {
        "study": config["study"],
        "protocol_version": config["protocol_version"],
        "scope": config["scope"],
        "seed": config["seed"],
        "windows": config["windows"],
        "outcomes": config["outcomes"],
        "exposures": config["exposures"],
        "covariates": config["covariates"],
        "missingness": config["missingness"],
        "correlations": config["correlations"],
        "multiplicity": config["multiplicity"],
        "joint_exposome": config["joint_exposome"],
        "bym2": config["bym2"],
        "evidence": config["evidence"],
        "input_hashes": dict(sorted(input_hashes.items())),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _slug(*parts: Any) -> str:
    text = "__".join(str(part) for part in parts if part not in (None, ""))
    text = re.sub(r"[^a-zA-Z0-9_.-]+", "-", text).strip("-.")
    if not text:
        raise ValueError("A model id cannot be empty")
    return text


def publication_tasks(
    config: Mapping[str, Any],
    spatial_ids: Sequence[str],
) -> list[ModelTask]:
    """Enumerate the registered 15 + 2 + 25 + 260 publication models."""
    outcomes = [str(value) for value in config["outcomes"]["confirmatory"]]
    tasks: list[ModelTask] = []
    for outcome in outcomes:
        for model_name in (
            "nb_nonspatial_exposure",
            "nb_bym2_null",
            "nb_bym2_exposure",
        ):
            tasks.append(
                ModelTask(
                    phase="primary",
                    model_id=_slug("primary", outcome, "pm25_hist", model_name),
                    outcome=outcome,
                    exposure="pm25_hist",
                    model_name=model_name,
                )
            )
    negative_outcome = str(config["outcomes"]["negative_control"][0])
    for exposure in ("pm25_hist", "no2"):
        tasks.append(
            ModelTask(
                phase="negative-controls",
                model_id=_slug("negative-control", negative_outcome, exposure),
                outcome=negative_outcome,
                exposure=exposure,
                model_name="nb_bym2_negative_control",
            )
        )
    variants = (
        "year_2018_core",
        "year_2019_core",
        "covid_2018_2020_core",
        "primary_access",
        "primary_rho_uniform",
    )
    for outcome in outcomes:
        for variant in variants:
            tasks.append(
                ModelTask(
                    phase="sensitivities",
                    model_id=_slug("sensitivity", outcome, "pm25_hist", variant),
                    outcome=outcome,
                    exposure="pm25_hist",
                    model_name=f"nb_bym2_exposure__{variant}",
                    variant=variant,
                )
            )
    for outcome in outcomes:
        for spatial_id in spatial_ids:
            tasks.append(
                ModelTask(
                    phase="commune-loo",
                    model_id=_slug("commune-loo", outcome, "pm25_hist", spatial_id),
                    outcome=outcome,
                    exposure="pm25_hist",
                    model_name="nb_bym2_exposure_commune_leave_one_out",
                    excluded_spatial_id=str(spatial_id),
                )
            )
    expected = {
        "primary": 15,
        "negative-controls": 2,
        "sensitivities": 25,
        "commune-loo": 260,
    }
    counts = {phase: sum(task.phase == phase for task in tasks) for phase in expected}
    if counts != expected:
        raise AssertionError(f"Unexpected publication task counts: {counts}")
    return tasks


def validate_netcdf_trace(
    path: Path,
    *,
    required_variables: Sequence[str] = (),
    expected_chains: int | None = None,
    expected_draws: int | None = None,
) -> dict[str, int]:
    """Open a trace through h5netcdf and validate its posterior contract."""
    import xarray as xr

    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise InferenceStateError(f"Missing or empty trace: {path}")
    try:
        tree = xr.open_datatree(path, engine="h5netcdf")
    except Exception as exc:
        raise InferenceStateError(f"Unreadable NetCDF trace {path}: {exc}") from exc
    try:
        if "posterior" not in tree.children:
            raise InferenceStateError(f"Trace has no posterior group: {path}")
        posterior = tree["posterior"].to_dataset()
        missing = sorted(set(required_variables).difference(posterior.data_vars))
        if missing:
            raise InferenceStateError(f"Trace {path} is missing posterior variables: {missing}")
        chains = int(posterior.sizes.get("chain", 0))
        draws = int(posterior.sizes.get("draw", 0))
        if expected_chains is not None and chains != int(expected_chains):
            raise InferenceStateError(
                f"Trace {path} has {chains} chains, expected {expected_chains}"
            )
        if expected_draws is not None and draws != int(expected_draws):
            raise InferenceStateError(
                f"Trace {path} has {draws} draws, expected {expected_draws}"
            )
        return {"chains": chains, "draws": draws}
    finally:
        tree.close()


def write_trace_atomic(
    idata: Any,
    path: Path,
    *,
    required_variables: Sequence[str],
    expected_chains: int,
    expected_draws: int,
) -> None:
    """Write and verify a trace before atomically publishing its final name."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    idata.to_netcdf(partial, engine="h5netcdf")
    validate_netcdf_trace(
        partial,
        required_variables=required_variables,
        expected_chains=expected_chains,
        expected_draws=expected_draws,
    )
    os.replace(partial, path)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(partial, path)


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    frame.to_csv(partial, index=False)
    os.replace(partial, path)


class InferenceRunStore:
    """Filesystem-backed state store with strict fingerprint reuse."""

    def __init__(self, output_dir: Path, fingerprint: str):
        self.output_dir = Path(output_dir)
        self.fingerprint = str(fingerprint)
        self.state_dir = self.output_dir / "run_state"
        self.models_dir = self.state_dir / "models"
        self.traces_dir = self.output_dir / "traces"

    def sidecar_path(self, task: ModelTask) -> Path:
        return self.models_dir / f"{task.model_id}.json"

    def trace_path(self, task: ModelTask) -> Path:
        return self.traces_dir / task.phase / f"{task.model_id}.nc"

    def _load_sidecar(self, task: ModelTask) -> dict[str, Any] | None:
        path = self.sidecar_path(task)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InferenceStateError(f"Unreadable model sidecar {path}: {exc}") from exc
        if record.get("schema_version") != STATE_SCHEMA_VERSION:
            raise InferenceStateError(f"Unsupported model sidecar schema: {path}")
        if record.get("model_id") != task.model_id:
            raise InferenceStateError(f"Sidecar/model id mismatch: {path}")
        if record.get("scientific_fingerprint") != self.fingerprint:
            raise InferenceConfigMismatch(
                f"Saved model {task.model_id} belongs to another configuration. "
                "Use a new --output-dir instead of mixing runs."
            )
        return record

    def reusable_record(
        self,
        task: ModelTask,
        *,
        resume: bool,
        rerun_failed: bool,
    ) -> dict[str, Any] | None:
        sidecar = self._load_sidecar(task)
        trace = self.trace_path(task)
        partial = trace.with_suffix(trace.suffix + ".partial")
        if partial.exists():
            partial.unlink()
        if sidecar is None:
            if trace.exists():
                raise InferenceStateError(
                    f"Orphan trace without sidecar: {trace}. Use a new --output-dir."
                )
            return None
        if not resume:
            raise InferenceStateError(
                f"State already exists for {task.model_id}; enable --resume or use a new output dir"
            )
        status = str(sidecar.get("status"))
        if status not in TERMINAL_STATUSES:
            return None
        if status == "failed_diagnostics" and rerun_failed:
            return None
        required_variables = sidecar.get("required_posterior_variables", [])
        sampling = sidecar.get("sampling", {})
        validate_netcdf_trace(
            trace,
            required_variables=required_variables,
            expected_chains=int(sampling["chains"]),
            expected_draws=int(sampling["draws"]),
        )
        return sidecar

    def save_record(
        self,
        task: ModelTask,
        idata: Any,
        *,
        diagnostics: Mapping[str, Any],
        effect: Mapping[str, Any] | None,
        extras: Mapping[str, Any] | None,
        required_variables: Sequence[str],
    ) -> dict[str, Any]:
        status = "ok" if diagnostics.get("diagnostics_passed") else "failed_diagnostics"
        sampling = {
            "chains": int(diagnostics["chains"]),
            "draws": int(diagnostics["draws"]),
            "tune": int(diagnostics["tune"]),
            "target_accept": float(diagnostics["target_accept"]),
            "attempt": int(diagnostics["attempt"]),
        }
        trace = self.trace_path(task)
        write_trace_atomic(
            idata,
            trace,
            required_variables=required_variables,
            expected_chains=sampling["chains"],
            expected_draws=sampling["draws"],
        )
        trace_hash = _sha256(trace)
        record = {
            "schema_version": STATE_SCHEMA_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            **task.as_dict(),
            "scientific_fingerprint": self.fingerprint,
            "status": status,
            "required_posterior_variables": list(required_variables),
            "sampling": sampling,
            "diagnostics": dict(diagnostics),
            "effect": None if effect is None else dict(effect),
            "extras": dict(extras or {}),
            "trace": {
                "path": str(trace.relative_to(self.output_dir)),
                "size_bytes": int(trace.stat().st_size),
                "sha256": trace_hash,
            },
        }
        atomic_write_json(self.sidecar_path(task), record)
        return record

    def records(self, tasks: Sequence[ModelTask]) -> list[dict[str, Any]]:
        records = []
        for task in tasks:
            record = self._load_sidecar(task)
            if record is not None:
                records.append(record)
        return records

    def status_rows(
        self,
        tasks: Sequence[ModelTask],
        *,
        resume: bool,
        rerun_failed: bool,
    ) -> list[dict[str, Any]]:
        rows = []
        for task in tasks:
            try:
                record = self.reusable_record(
                    task, resume=resume, rerun_failed=rerun_failed
                )
                state = "pending" if record is None else str(record["status"])
            except InferenceConfigMismatch:
                raise
            except InferenceStateError as exc:
                state = "invalid"
                rows.append({**task.as_dict(), "state": state, "reason": str(exc)})
                continue
            rows.append({**task.as_dict(), "state": state, "reason": None})
        return rows

    def preflight(
        self,
        tasks: Sequence[ModelTask],
        *,
        resume: bool,
        rerun_failed: bool,
        minimum_free_gib: float = 15.0,
    ) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        rows = self.status_rows(tasks, resume=resume, rerun_failed=rerun_failed)
        pending = sum(row["state"] == "pending" for row in rows)
        free_bytes = int(shutil.disk_usage(self.output_dir).free)
        existing_sizes = [
            int(record["trace"]["size_bytes"])
            for record in self.records(tasks)
            if record.get("trace", {}).get("size_bytes")
        ]
        average_trace_bytes = int(sum(existing_sizes) / len(existing_sizes)) if existing_sizes else None
        projected_bytes = (
            int(average_trace_bytes * pending * 1.2) if average_trace_bytes is not None else None
        )
        minimum_bytes = int(float(minimum_free_gib) * 1024**3)
        required_bytes = max(minimum_bytes, projected_bytes or 0)
        result = {
            "free_gib": free_bytes / 1024**3,
            "minimum_free_gib": float(minimum_free_gib),
            "pending_models": pending,
            "completed_models": sum(row["state"] in TERMINAL_STATUSES for row in rows),
            "invalid_models": sum(row["state"] == "invalid" for row in rows),
            "average_trace_mib": (
                average_trace_bytes / 1024**2 if average_trace_bytes is not None else None
            ),
            "projected_pending_gib": (
                projected_bytes / 1024**3 if projected_bytes is not None else None
            ),
            "passed": bool(pending == 0 or free_bytes >= required_bytes),
        }
        if result["invalid_models"]:
            raise InferenceStateError(
                f"State preflight found {result['invalid_models']} invalid model records; "
                "inspect --phase status before sampling"
            )
        if not result["passed"]:
            raise InferenceStateError(
                f"Storage preflight failed: {result['free_gib']:.1f} GiB free, "
                f"at least {required_bytes / 1024**3:.1f} GiB required"
            )
        return result
