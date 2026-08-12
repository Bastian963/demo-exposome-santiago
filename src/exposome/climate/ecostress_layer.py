"""Build the ECOSTRESS land surface temperature layer for a study.

Orchestration lives here rather than in the CLI script so the layer has an
importable in-process runner like every other catalogued layer
(``config/runner_parity.yaml``), and so the collection logic is unit-testable
without a subprocess.

See :mod:`exposome.climate.fetch_ecostress` for the provider-facing pieces and
for why this is the one layer that does not come from Earth Engine.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from tqdm import tqdm

from .. import config as _config
from . import fetch_ecostress as fe

LAYER_ID = "climate_lst_ecostress"
ID_COLUMN = "spatial_id"


def _settings(city: str) -> Mapping[str, Any]:
    return _config.load_config(city).get(LAYER_ID, {}) or {}


def _windows_from_settings(settings: Mapping[str, Any]) -> tuple[fe.SolarWindow, ...]:
    raw = settings.get("solar_windows")
    if not raw:
        return fe.DEFAULT_WINDOWS
    return tuple(
        fe.SolarWindow(
            str(item["name"]), float(item["start_hour"]), float(item["end_hour"])
        )
        for item in raw
    )


def build_unit_labels(
    grid: fe.StudyGrid, units: Any, id_column: str = ID_COLUMN
) -> tuple[np.ndarray, list[Any]]:
    """Rasterize the spatial units once into a label grid.

    Deliberately hoisted out of the granule loop: the geometries never change,
    so rasterizing them per granule would redo hundreds of Mpx of work
    thousands of times over a full run.  Label 0 is background; unit *i* is
    label *i + 1*.
    """
    from rasterio.features import rasterize

    identifiers = list(units[id_column])
    projected = units.to_crs(grid.crs)
    shapes = [(geom, index) for index, geom in enumerate(projected.geometry, start=1)]
    labels = rasterize(
        shapes, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="int32"
    )
    return labels, identifiers


def unit_summaries(
    values: np.ndarray,
    mask: np.ndarray,
    labels: np.ndarray,
    identifiers: Sequence[Any],
    id_column: str = ID_COLUMN,
) -> list[dict[str, Any]]:
    """Per-unit mean/max/count for a single granule, via the label grid.

    Cached alongside the accumulators so the observation-level record survives
    the streaming reduction: the tabular product can be redefined later without
    re-downloading a byte.
    """
    from scipy import ndimage

    n_units = len(identifiers)
    selected = (labels > 0) & mask
    flat_labels = labels[selected]
    flat_values = values[selected]

    counts = np.bincount(flat_labels, minlength=n_units + 1)[1:]
    sums = np.bincount(flat_labels, weights=flat_values, minlength=n_units + 1)[1:]
    if flat_values.size:
        maxima = np.atleast_1d(
            ndimage.maximum(
                flat_values, labels=flat_labels, index=np.arange(1, n_units + 1)
            )
        )
    else:
        maxima = np.full(n_units, np.nan)

    rows: list[dict[str, Any]] = []
    for index, identifier in enumerate(identifiers):
        count = int(counts[index])
        rows.append(
            {
                id_column: identifier,
                "n_pixels": count,
                "lst_mean_c": float(sums[index] / count) if count else None,
                "lst_max_c": (
                    float(maxima[index])
                    if count and np.isfinite(maxima[index])
                    else None
                ),
            }
        )
    return rows


def build_climate_lst_ecostress_layer(
    city: str,
    cache_dir: str | Path = "cache",
    out_dir: str | Path = "data/processed",
    *,
    start: str | None = None,
    end: str | None = None,
    version: str | None = None,
    max_qc_level: int | None = None,
    checkpoint_interval: int = 25,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Collect ECOSTRESS LST and write the native composite for one study.

    LONG-RUNNING and network-bound.  ``city`` is the study id, matching the
    convention the layer runner adapter uses.
    """
    from ..studies import load_study

    settings = _settings(city)
    collection = settings.get("collection", {})
    period = settings.get("period", {})
    quality = settings.get("quality", {})

    start = start or str(period.get("start", "2019-01-01"))
    end = end or str(period.get("end", "2026-01-01"))
    version = version or str(collection.get("version", fe.DEFAULT_VERSION))
    if max_qc_level is None:
        max_qc_level = int(quality.get("max_qc_level", 1))
    windows = _windows_from_settings(settings)

    context = load_study(city)
    units = context.spatial_units
    metric_crs = str(context.metric_crs)
    grid = fe.build_study_grid(tuple(units.to_crs(metric_crs).total_bounds), metric_crs)

    geographic = units.to_crs(context.location.geographic_crs)
    west, south, east, north = (float(value) for value in geographic.total_bounds)
    centroid_lon = (west + east) / 2.0

    print(
        f"{city}: grid {grid.width}x{grid.height} @70 m in {metric_crs} "
        f"({grid.width * grid.height / 1e6:.1f} Mpx)"
    )

    granules = fe.search_granules(
        (west, south, east, north),
        start,
        end,
        version=version,
        short_name=str(collection.get("short_name", fe.SHORT_NAME)),
    )
    print(f"CMR: {len(granules)} granules for {start} .. {end}")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = cache_dir / f"accumulators_{start}_{end}_v{version}.npz"
    summary_path = cache_dir / f"granule_unit_summaries_{start}_{end}_v{version}.csv"

    if checkpoint.exists():
        accumulators = fe.AccumulatorSet.load(checkpoint)
        print(f"Resuming: {len(accumulators.processed)} granules already folded in")
    else:
        accumulators = fe.AccumulatorSet(shape=grid.shape, windows=windows)

    selected = list(
        fe.iter_granule_windows(
            granules, centroid_lon, windows, skip=accumulators.processed
        )
    )
    print(f"{len(selected)} granules in a solar window and not yet processed")
    if dry_run:
        by_window: dict[str, int] = {}
        for _, info in selected:
            by_window[info["window"]] = by_window.get(info["window"], 0) + 1
        print(f"Dry run; per window: {by_window}")
        return {"dry_run": True, "selected": len(selected), "per_window": by_window}

    # Fail on a missing credential here, not hundreds of granules deep.
    fe.ensure_earthdata_auth()

    labels, identifiers = build_unit_labels(grid, units)
    print(
        f"Rasterized {len(identifiers)} units once: "
        f"{int((labels > 0).sum()) / 1e6:.1f} Mpx inside the study"
    )

    summaries: list[dict[str, Any]] = []
    failures = 0
    for index, (granule, info) in enumerate(
        tqdm(selected, desc=f"{LAYER_ID} [{city}]", unit="granule"), start=1
    ):
        try:
            urls = fe.granule_asset_urls(granule)
            values, mask = fe.read_granule_to_grid(
                urls, grid, max_qc_level=max_qc_level
            )
        except Exception as exc:  # one bad granule must not lose the whole run
            failures += 1
            tqdm.write(f"  SKIP {info['granule_id']}: {exc}")
            continue

        kept = accumulators.update(info["window"], values, mask)
        accumulators.mark_processed(info["granule_id"])
        for row in unit_summaries(values, mask, labels, identifiers):
            row.update(
                {
                    "granule_id": info["granule_id"],
                    "tile": info["tile"],
                    "acquired_utc": info["acquired_utc"].isoformat(),
                    "solar_hour": round(info["solar_hour"], 3),
                    "window": info["window"],
                }
            )
            summaries.append(row)
        if kept == 0:
            tqdm.write(f"  {info['granule_id']}: fully masked (cloud/water/QC)")

        if checkpoint_interval > 0 and index % checkpoint_interval == 0:
            accumulators.save(checkpoint)
            summaries = _flush_summaries(summaries, summary_path)

    accumulators.save(checkpoint)
    _flush_summaries(summaries, summary_path)

    out_dir = Path(out_dir)
    bands: dict[str, np.ndarray] = {}
    descriptions: dict[str, str] = {}
    for name, acc in accumulators.accumulators.items():
        bands[f"lst_{name}_mean_c"] = acc.mean()
        bands[f"lst_{name}_max_c"] = acc.peak()
        bands[f"lst_{name}_n_obs"] = acc.count.astype("float32")
        descriptions[f"lst_{name}_mean_c"] = f"Mean LST, {name} solar window (degC)"
        descriptions[f"lst_{name}_max_c"] = f"Max LST, {name} solar window (degC)"
        descriptions[f"lst_{name}_n_obs"] = f"Clear-sky observation count, {name} window"

    raster = fe.write_composite(
        out_dir / f"{LAYER_ID}_native.tif", bands, grid, descriptions=descriptions
    )

    coverage = {
        name: {
            "observed_px": int((acc.count > 0).sum()),
            "grid_px": int(acc.count.size),
            "max_obs_per_px": int(acc.count.max()) if acc.count.size else 0,
        }
        for name, acc in accumulators.accumulators.items()
    }
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study": context.study.id,
        "layer": LAYER_ID,
        "product_kind": "raster",
        "provider": str(collection.get("provider", "NASA Earthdata LP DAAC")),
        "collection": f"{collection.get('short_name', fe.SHORT_NAME)} v{version}",
        "native_resolution_m": 70,
        "units": "degC",
        "crs": metric_crs,
        "period": {"start": start, "end": end},
        "solar_windows": [
            {"name": w.name, "start_hour": w.start, "end_hour": w.end}
            for w in accumulators.windows
        ],
        # Explicit so the `band:` indices in config/layers/climate_lst_ecostress.yaml
        # can be checked against the file instead of inferred from dict order.
        "band_order": {name: index for index, name in enumerate(bands, start=1)},
        "granules_folded": len(accumulators.processed),
        "granules_failed": failures,
        "coverage": coverage,
        "quantity": (
            "Radiative skin temperature. NOT 2 m air temperature; does not "
            "replace climate_heat (ERA5-Land T2M)."
        ),
        "outputs": [raster.name],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{LAYER_ID}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {raster}")
    if failures:
        print(f"WARNING: {failures} granules failed and were skipped")
    return metadata


def _flush_summaries(rows: list[dict[str, Any]], path: Path) -> list[dict[str, Any]]:
    """Append buffered summary rows and return a fresh buffer."""
    if not rows:
        return rows
    pd.DataFrame(rows).to_csv(
        path, mode="a", header=not path.exists(), index=False
    )
    return []
