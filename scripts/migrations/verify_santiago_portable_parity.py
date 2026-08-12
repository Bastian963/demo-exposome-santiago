#!/usr/bin/env python3
"""Verify legacy-to-canonical parity for catalogued Santiago master layers."""
from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
from pandas.api.types import is_bool_dtype


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from exposome.layers import load_layer_catalog  # noqa: E402
from build_master_exposome import LAYER_SPECS  # noqa: E402


def _sources(catalog) -> dict[str, str]:
    return {
        str(spec["name"]): str(spec["csv"]).removesuffix(".csv")
        for spec in LAYER_SPECS
        if str(spec["name"]) in catalog.layers
    }


def _primary_csv(directory: Path) -> Path:
    candidates = [path for path in directory.glob("*.csv") if "daily" not in path.name]
    if len(candidates) != 1:
        raise ValueError(f"Expected one primary CSV in {directory}, found {candidates}")
    return candidates[0]


def _equal_series(old: pd.Series, new: pd.Series, layer_id: str, column: str) -> None:
    if is_bool_dtype(old) or is_bool_dtype(new):
        if old.astype(bool).tolist() != new.astype(bool).tolist():
            raise AssertionError(f"{layer_id}.{column} boolean values changed")
        return
    old_numeric = pd.to_numeric(old, errors="coerce")
    new_numeric = pd.to_numeric(new, errors="coerce")
    if old_numeric.notna().any() or new_numeric.notna().any():
        delta = (old_numeric - new_numeric).abs().max()
        if pd.notna(delta) and float(delta) > 1e-9:
            raise AssertionError(f"{layer_id}.{column} changed by {delta}")
        return
    if old.astype(str).tolist() != new.astype(str).tolist():
        raise AssertionError(f"{layer_id}.{column} text values changed")


def main() -> None:
    legacy = ROOT / "data" / "processed"
    canonical = legacy / "cl" / "santiago" / "santiago_communes"
    catalog = load_layer_catalog()
    for layer_id, stem in _sources(catalog).items():
        old = pd.read_csv(legacy / f"{stem}.csv").sort_values("name").reset_index(drop=True)
        new = pd.read_csv(
            _primary_csv(canonical / layer_id), dtype={"spatial_id": str}
        ).sort_values("name").reset_index(drop=True)
        if old["name"].tolist() != new["name"].tolist():
            raise AssertionError(f"{layer_id}: commune order or names changed")
        if not new["spatial_id"].str.fullmatch(r"13\d{3}").all():
            raise AssertionError(f"{layer_id}: output does not contain five-digit CUT values")
        for column in catalog.get(layer_id).master["required_columns"]:
            _equal_series(old[column], new[column], layer_id, column)
        print(f"{layer_id}: OK")
    master = pd.read_csv(canonical / "master.csv", dtype={"spatial_id": str})
    if len(master) != 52 or not master["spatial_id"].str.fullmatch(r"13\d{3}").all():
        raise AssertionError("Canonical portable master does not have 52 CUT units")
    print(f"master: OK ({master.shape[0]} rows × {master.shape[1]} columns)")


if __name__ == "__main__":
    main()
