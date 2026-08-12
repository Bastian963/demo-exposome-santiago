"""Explicit retirement gates for legacy ``scripts/run_*.py`` adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from .layers import LayerCatalog, load_layer_catalog
from .runners import has_importable_runner


DEFAULT_PARITY_PATH = Path(__file__).resolve().parents[2] / "config" / "runner_parity.yaml"
ALLOWED_STATES = frozenset({"adapter", "canonical", "retired"})


@dataclass(frozen=True)
class RunnerParityRecord:
    layer_id: str
    state: str
    legacy_script: Path | None
    registered: bool
    gates: Mapping[str, bool]

    @property
    def retirement_ready(self) -> bool:
        return self.registered and bool(self.gates) and all(self.gates.values())


def load_runner_parity(
    path: str | Path = DEFAULT_PARITY_PATH,
    *,
    catalog: LayerCatalog | None = None,
) -> tuple[RunnerParityRecord, ...]:
    """Load an exact catalog-wide gate matrix and reject premature retirement."""
    catalog = catalog or load_layer_catalog()
    path = Path(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported runner parity schema: {path}")
    required = payload.get("required_gates")
    layers = payload.get("layers")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ValueError("runner parity required_gates must be a list of strings")
    if not isinstance(layers, Mapping):
        raise ValueError("runner parity layers must be a mapping")
    expected = set(catalog.ids)
    actual = set(map(str, layers))
    if expected != actual:
        raise ValueError(
            "runner parity catalog mismatch; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )

    records: list[RunnerParityRecord] = []
    repo_root = path.resolve().parents[1]
    for layer_id in catalog.ids:
        raw = layers[layer_id]
        if not isinstance(raw, Mapping):
            raise ValueError(f"runner parity entry for {layer_id!r} must be a mapping")
        state = str(raw.get("state") or "")
        if state not in ALLOWED_STATES:
            raise ValueError(f"invalid runner state for {layer_id!r}: {state!r}")
        raw_gates = raw.get("gates", {})
        if not isinstance(raw_gates, Mapping):
            raise ValueError(f"runner gates for {layer_id!r} must be a mapping")
        unknown = sorted(set(map(str, raw_gates)) - set(required))
        if unknown:
            raise ValueError(f"unknown runner gates for {layer_id!r}: {unknown}")
        gates = {gate: raw_gates.get(gate) is True for gate in required}
        command = catalog.get(layer_id).command
        script = repo_root / command[0] if command and command[0].endswith(".py") else None
        record = RunnerParityRecord(
            layer_id=layer_id,
            state=state,
            legacy_script=script,
            registered=has_importable_runner(layer_id),
            gates=gates,
        )
        if state == "retired" and not record.retirement_ready:
            raise ValueError(f"Layer {layer_id!r} is marked retired before all gates pass")
        if state != "retired" and script is not None and not script.is_file():
            raise FileNotFoundError(
                f"Layer {layer_id!r} still needs its compatibility script: {script}"
            )
        if state == "retired" and script is not None and script.exists():
            raise ValueError(f"Retired Layer {layer_id!r} still has script {script}")
        records.append(record)
    return tuple(records)
