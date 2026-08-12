"""Decide what a buffer radius means for a given indicator.

The point extractor must never claim more spatial resolution than a product
supports (ADR 0004 §5, ADR 0012 §2).  This module turns the declarations in
:data:`exposome.spatial_support.INDICATOR_SUPPORT` into two numbers a sampler
can act on: the **effective support** in ground metres at a given latitude, and
whether a requested radius resolves anything at that support.

It contains no I/O and no geometry.  Everything here is a pure function of the
declared support plus a latitude.
"""
from __future__ import annotations

from typing import Any, Mapping

from .spatial_support import INDICATOR_SUPPORT

# The repo's own convention for degrees to metres: ``INDICATOR_SUPPORT``
# declares a 0.01 degree grid as 1113.2 m, which is 0.01 * 111320.  Keeping the
# same constant means a converted degree resolution equals the metre resolution
# the catalog already publishes for the same product.
METRES_PER_DEGREE = 111_320.0

#: Offered by default in the UI and the CLI.  ``0`` means the containing cell.
DEFAULT_RADII: tuple[int, ...] = (0, 300, 500, 1000)

RESOLVED = "resolved"
SUB_OBSERVATION = "sub_observation"
NOT_APPLICABLE = "not_applicable"

RASTER_BLOCK = "raster_block"
ADMINISTRATIVE_UNIT = "administrative_unit"
VECTOR_QUERY = "vector_query"
COMPOSITE = "composite"

_KIND_BY_DOWNLOADED = {
    "raster_grid": RASTER_BLOCK,
    "administrative_unit": ADMINISTRATIVE_UNIT,
    "vector_features": VECTOR_QUERY,
    "component_specific": COMPOSITE,
}


class UnknownIndicator(KeyError):
    """The indicator has no declared spatial support."""


def _record(indicator_id: str) -> Mapping[str, Any]:
    try:
        return INDICATOR_SUPPORT[indicator_id]
    except KeyError as error:
        raise UnknownIndicator(
            f"{indicator_id!r} has no entry in INDICATOR_SUPPORT; declare its support "
            "before extracting it at a point"
        ) from error


def has_support(indicator_id: str) -> bool:
    return indicator_id in INDICATOR_SUPPORT


def estimand_kind(indicator_id: str) -> str:
    """Classify what a point query returns for this indicator.

    ``raster_block`` averages over a neighbourhood; ``administrative_unit``
    returns the containing unit and never blends across boundaries;
    ``vector_query`` counts features at query time; ``composite`` has no single
    support because each component keeps its own.
    """
    record = _record(indicator_id)
    downloaded = record.get("downloaded") or {}
    kind = _KIND_BY_DOWNLOADED.get(str(downloaded.get("kind")))
    if kind is None:
        raise UnknownIndicator(
            f"{indicator_id!r} declares an unmapped downloaded kind "
            f"{downloaded.get('kind')!r}"
        )
    return kind


def resolution_metres(resolution: Mapping[str, Any] | None, latitude: float) -> float | None:
    """Convert a declared resolution to ground metres, taking the larger axis.

    Anisotropic footprints are reduced to their largest dimension on purpose:
    a buffer that does not span the long axis of an observation has not
    averaged over an independent measurement.  For NO2 that means 7000 m, not
    3500 m.

    Degrees are converted at ``latitude``.  Longitude degrees shrink by
    ``cos(latitude)`` while latitude degrees do not, so the larger axis of a
    square degree cell is always the north-south one.
    """
    if not resolution:
        return None
    unit = str(resolution.get("unit") or "").lower()
    if unit == "vector":
        return None

    candidates: list[float] = []
    if resolution.get("value") is not None:
        candidates.append(float(resolution["value"]))
    for key in ("x", "y", "y_max", "x_max"):
        if resolution.get(key) is not None:
            candidates.append(float(resolution[key]))
    if not candidates:
        return None

    largest = max(candidates)
    if unit == "degree":
        # cos(latitude) only shrinks the east-west axis, so the north-south
        # extent bounds the cell and needs no latitude correction.
        return largest * METRES_PER_DEGREE
    return largest


def observation_support_m(indicator_id: str, latitude: float) -> float | None:
    """Ground metres of the footprint that can actually support a measurement."""
    record = _record(indicator_id)
    return resolution_metres((record.get("observation") or {}).get("resolution"), latitude)


def analysis_support_m(indicator_id: str, latitude: float) -> float | None:
    """Ground metres of the grid the indicator is actually computed on."""
    record = _record(indicator_id)
    return resolution_metres((record.get("analysis") or {}).get("resolution"), latitude)


def effective_support_m(indicator_id: str, latitude: float) -> float | None:
    """The coarsest of the observation footprint and the analysis grid.

    Both floors are real and neither dominates in general:

    * ``no2`` is analysed on a 1113 m grid but a TROPOMI observation covers
      3.5 x 5.5-7 km, so the footprint is the binding constraint.
    * ``canopy`` is *observed* at 1 m, but what is published is a canopy
      *fraction* aggregated to 30 m.  Height at 1 m and fraction at 30 m are
      different quantities; the published one has 30 m support, so the analysis
      grid binds. Taking the observation alone would advertise 1 m support for a
      30 m product.

    Taking the maximum is therefore the only choice that never overclaims.
    """
    observation = observation_support_m(indicator_id, latitude)
    analysis = analysis_support_m(indicator_id, latitude)
    known = [value for value in (observation, analysis) if value is not None]
    return max(known) if known else None


def radius_status(indicator_id: str, radius_m: float, latitude: float) -> str:
    """Say whether a radius resolves anything for this indicator.

    ``not_applicable`` is returned for every non-raster estimand: an
    administrative value has no intra-unit variation to average, and a
    composite has no single support.
    """
    if estimand_kind(indicator_id) != RASTER_BLOCK:
        return NOT_APPLICABLE
    support = effective_support_m(indicator_id, latitude)
    if support is None:
        return NOT_APPLICABLE
    return RESOLVED if 2 * float(radius_m) >= support else SUB_OBSERVATION


def delivered_support_m(indicator_id: str, radius_m: float, latitude: float) -> float | None:
    """The support actually delivered: never finer than the product allows."""
    support = effective_support_m(indicator_id, latitude)
    if support is None:
        return None
    return max(2 * float(radius_m), support)


def describe_radius(indicator_id: str, radius_m: float, latitude: float) -> dict[str, Any]:
    """Everything the output schema needs about one (indicator, radius) pair."""
    return {
        "indicator_id": indicator_id,
        "estimand_kind": estimand_kind(indicator_id),
        "radius_m": None if estimand_kind(indicator_id) != RASTER_BLOCK else float(radius_m),
        "radius_status": radius_status(indicator_id, radius_m, latitude),
        "support_m": delivered_support_m(indicator_id, radius_m, latitude),
        "observation_support_m": observation_support_m(indicator_id, latitude),
        "analysis_support_m": analysis_support_m(indicator_id, latitude),
    }


def emits_within_buffer_sd(indicator_id: str, radius_m: float, latitude: float) -> bool:
    """Whether ``sd_within_buffer`` is meaningful for this pair.

    Under ``sub_observation`` every contributing cell sits inside a single
    observation footprint, so the standard deviation collapses toward zero and
    would read as *high confidence* exactly where the data is least informative.
    NO2 is in that regime at every offered radius.  Suppressing the number is
    more honest than publishing a misleadingly small one (ADR 0012 §4).
    """
    return radius_status(indicator_id, radius_m, latitude) == RESOLVED
