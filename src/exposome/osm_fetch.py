"""Shared OSM/Overpass fetch helper: endpoint fallback + exponential backoff.

Multiple layers (greenspace_access, healthcare, food_environment,
walkability, social_infrastructure) each download from OpenStreetMap via
osmnx/Overpass and each used to implement its own retry loop against a
single hardcoded endpoint (``overpass-api.de``). Running several studies in
parallel against that one endpoint saturates its per-IP connection limit and
every layer's retries fail together, aborting the whole batch. This module
centralizes the fix social_infrastructure.py already had: rotate across
multiple Overpass mirrors, with exponential backoff between attempts on the
same mirror.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
from typing import Any, Callable, Iterable, Sequence, TypeVar

import geopandas as gpd
import osmnx as ox
import pandas as pd
from osmnx._errors import InsufficientResponseError  # not re-exported publicly

# osmnx's own on-disk HTTP response cache (default "./cache") is redundant here
# -- every caller of this module already checkpoints at the region/tile level
# itself -- and this repo lives inside a Dropbox-synced folder. Confirmed via
# direct testing (2026-07-27): writing a trivial ~0.3kB cached response inside
# the synced tree took 46s after the HTTP response had already arrived, purely
# from Dropbox's sync daemon reacting to the write; the same request outside
# Dropbox saved instantly. Disabling osmnx's cache removes that latency
# entirely with no loss of resume behavior.
ox.settings.use_cache = False

_T = TypeVar("_T")

# overpass-api.de and overpass.kumi.systems were both unreachable for a
# sustained multi-day window (confirmed 2026-08-03 through 2026-08-05: 504
# / connection timeout on every direct curl check, not a transient blip).
# overpass.openstreetmap.fr was confirmed reachable and returning real
# matching data (same probe query, same result) during that same outage,
# including for the actual heavier leisure/landuse polygon queries this
# module makes (not just a trivial single-node lookup) -- a 237 km2 test
# query returned 20 MB of real data in ~21s. overpass.osm.ch also responded
# 200 with valid (if sparser) Overpass JSON.
#
# overpass.kumi.systems was removed from this list entirely on 2026-08-05:
# unlike overpass-api.de (which fails fast with a clean 504), kumi.systems
# now *accepts* the TCP/TLS connection and serves a valid cert
# (confirmed via `openssl s_client`, also answering as
# overpass.private.coffee) but then never sends an HTTP response. A
# real san_juan_departamentos run hung on it for 30-40+ minutes with zero
# log output despite the 300s attempt_timeout_s deadline, on two separate
# attempts, even though an isolated unit-level test of the same
# `_call_with_deadline` mechanism against the same URL DID interrupt
# correctly at the configured deadline -- something about the full
# pipeline process (likely GEE client activity from an immediately
# preceding layer) prevents the interrupt from reaching this call in
# practice. Rather than chase that interaction further, drop the one
# endpoint that fails silently/indefinitely -- a clean, fast failure
# (overpass-api.de's 504) is a solved problem (endpoint fallback handles
# it); a silent hang defeats the whole point of an attempt deadline.
_DEFAULT_ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.openstreetmap.fr/api",
    "https://overpass.osm.ch/api",
)

# Largest tile Overpass reliably answers for a *green/polygon* tag query
# (parks, gardens -- complex geometry, expensive per unit area). Rural units
# with dense natural landcover (Bogota's Sumapaz paramo, 780 km2) time out
# well before urban units of the same degree span, so tiles are kept near the
# largest single-region query observed to succeed (~0.16 deg / 65 km2,
# Usaquen). greenspace_access.py is the only caller that needs this value.
GREEN_TAG_MAX_TILE_SPAN_DEG = 0.08

# Largest tile Overpass reliably answers for a simple *point* tag query
# (amenity/shop nodes -- healthcare, food_environment). These are far
# cheaper per unit area than green polygons: santiago_communes's real study
# bbox (1.945 deg span) and buenos_aires_amba's (1.67 deg) both already run
# healthcare.py's OLD hardcoded grid_size=2 successfully in production, i.e.
# tiles up to ~0.97 deg/side are proven safe for this tag class. 1.0 deg
# keeps that exact grid_size=2 for both (no regression) while still scaling
# up meaningfully for a whole-province AOI: san_juan_departamentos's real
# study bbox is 4.24 deg span, which was previously hardcoded to the same
# grid_size=2 (tiles of ~10,900 km2, ~17x osmnx's own default max query
# area) and failed outright on every tile/tag -- confirmed 2026-08-03 that
# this was tile size, not Overpass availability: a trivial ~100 km2 query
# against the same province succeeded instantly. At 1.0 deg San Juan gets
# grid_size=5 (25 tiles of ~0.85 deg/side, under Santiago's proven ceiling).
POINT_TAG_MAX_TILE_SPAN_DEG = 1.0


def tile_grid_size_for_bbox(bbox: Sequence[float], max_tile_span_deg: float) -> int:
    """Number of tiles per side so no tile exceeds ``max_tile_span_deg``.

    Callers must pass the max tile span tuned for their own tag class --
    green/polygon queries and simple point-tag queries tolerate very
    different tile sizes (see ``GREEN_TAG_MAX_TILE_SPAN_DEG`` and
    ``POINT_TAG_MAX_TILE_SPAN_DEG`` above).
    """
    west, south, east, north = (float(value) for value in bbox)
    span = max(east - west, north - south)
    return max(1, math.ceil(span / max_tile_span_deg))


class OverpassAttemptTimeout(TimeoutError):
    """One Overpass endpoint attempt exceeded its wall-clock deadline."""


def _call_with_deadline(
    fn: Callable[[], _T],
    *,
    timeout_s: float | None,
    label: str,
) -> _T:
    """Call ``fn`` with a POSIX wall-clock deadline when available.

    OSMnx retries HTTP 429/504 responses recursively, outside the retry budget
    in this module. On POSIX the alarm interrupts that internal recursion so
    endpoint fallback remains finite. Non-main threads and platforms without
    ``setitimer`` retain the underlying request timeout as their guard.
    """
    if (
        timeout_s is None
        or timeout_s <= 0
        or not hasattr(signal, "SIGALRM")
        or not hasattr(signal, "setitimer")
        or threading.current_thread() is not threading.main_thread()
    ):
        return fn()

    timeout_s = float(timeout_s)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def timeout_handler(signum: int, frame: Any) -> None:
        del signum, frame
        raise OverpassAttemptTimeout(
            f"Overpass attempt exceeded {timeout_s:.0f}s"
            f"{f' for {label}' if label else ''}"
        )

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        previous_delay, previous_interval = previous_timer
        if previous_delay > 0:
            elapsed = time.monotonic() - started
            signal.setitimer(
                signal.ITIMER_REAL,
                max(previous_delay - elapsed, 1e-6),
                previous_interval,
            )


def overpass_endpoints(extra: Iterable[str] | None = None) -> list[str]:
    """Ordered, deduplicated list of Overpass endpoints to try.

    ``$OSMNX_OVERPASS_URL`` (if set) is tried first, then any endpoints
    passed explicitly via ``extra`` (e.g. a layer's own config), then the
    shared defaults.
    """
    candidates = [os.environ.get("OSMNX_OVERPASS_URL"), *(extra or []), *_DEFAULT_ENDPOINTS]
    seen: set[str] = set()
    result: list[str] = []
    for url in candidates:
        if not url:
            continue
        url = url.rstrip("/")
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def call_with_overpass_fallback(
    fn: Callable[[], _T],
    *,
    endpoints: Sequence[str] | None = None,
    attempts: int = 3,
    attempt_timeout_s: float | None = 180.0,
    base_sleep: float = 20.0,
    backoff: float = 3.0,
    label: str = "",
    log: Callable[[str], None] = print,
) -> _T:
    """Call ``fn()`` rotating ``ox.settings.overpass_url`` across ``endpoints``.

    Each endpoint gets up to ``attempts`` tries with exponential backoff
    (``base_sleep``, ``base_sleep * backoff``, ...) between them. Any
    exception from ``fn`` (including osmnx's own ``TypeError`` on malformed
    responses from an overloaded server) is treated as retryable. Each
    attempt also has a wall-clock deadline because OSMnx recursively retries
    429/504 responses without a maximum. The
    original ``ox.settings.overpass_url`` is always restored on exit.
    Raises ``ConnectionError`` if every endpoint is exhausted.
    """
    endpoints = list(endpoints) if endpoints is not None else overpass_endpoints()
    if not endpoints:
        raise ConnectionError("No Overpass endpoints configured")
    prefix = f"  [{label}]" if label else " "
    original_url = ox.settings.overpass_url
    last_exc: Exception | None = None
    try:
        for endpoint in endpoints:
            ox.settings.overpass_url = endpoint
            sleep_s = base_sleep
            for attempt in range(attempts):
                try:
                    deadline = (
                        f", deadline {float(attempt_timeout_s):.0f}s"
                        if attempt_timeout_s is not None
                        else ""
                    )
                    log(
                        f"{prefix} attempt {attempt + 1}/{attempts} via "
                        f"{endpoint}{deadline}"
                    )
                    return _call_with_deadline(
                        fn,
                        timeout_s=attempt_timeout_s,
                        label=label,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < attempts - 1:
                        log(
                            f"{prefix} retry {attempt + 1}/{attempts - 1} via {endpoint} "
                            f"after {type(exc).__name__}, waiting {sleep_s:.0f}s..."
                        )
                        time.sleep(sleep_s)
                        sleep_s *= backoff
            log(f"{prefix} endpoint failed: {endpoint}")
        raise ConnectionError(
            f"OSM/Overpass call failed after trying {len(endpoints)} endpoint(s)"
            f"{f' for {label}' if label else ''}"
        ) from last_exc
    finally:
        ox.settings.overpass_url = original_url


def _tile_query_key(
    bbox: Sequence[float],
    tags: dict[str, Any],
    grid_size: int,
) -> str:
    payload = json.dumps(
        {
            "bbox": [float(value) for value in bbox],
            "tags": tags,
            "grid_size": int(grid_size),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _write_geojson_atomic(frame: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.partial{path.suffix}")
    try:
        frame.to_file(temporary, driver="GeoJSON")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _bbox_tiles(
    bbox: Sequence[float],
    grid_size: int,
) -> list[tuple[float, float, float, float]]:
    """Split ``(west, south, east, north)`` into a regular tile grid."""
    if len(bbox) != 4:
        raise ValueError("bbox must contain west, south, east, north")
    west, south, east, north = (float(value) for value in bbox)
    if west >= east or south >= north:
        raise ValueError(f"Invalid bbox: {(west, south, east, north)}")
    if grid_size < 1:
        raise ValueError("grid_size must be at least 1")

    lon_step = (east - west) / grid_size
    lat_step = (north - south) / grid_size
    return [
        (
            west + col * lon_step,
            south + row * lat_step,
            west + (col + 1) * lon_step,
            south + (row + 1) * lat_step,
        )
        for row in range(grid_size)
        for col in range(grid_size)
    ]


def _reset_osm_index(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Preserve OSM ``element/id`` identifiers as ordinary columns."""
    if isinstance(frame.index, pd.RangeIndex) and frame.index.name is None:
        return frame.copy()
    index_names = [name for name in frame.index.names if name is not None]
    if index_names and all(name not in frame.columns for name in index_names):
        return frame.reset_index()
    return frame.reset_index(drop=True)


def _deduplicate_osm_features(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Deduplicate tiled/overlapping OSM results without losing anonymous rows."""
    if frame.empty:
        return frame.reset_index(drop=True)
    result = frame.copy()
    has_osm_id = {"element", "id"}.issubset(result.columns)
    if has_osm_id:
        identified = result["element"].notna() & result["id"].notna()
        with_id = result.loc[identified].drop_duplicates(["element", "id"])
        without_id = result.loc[~identified].copy()
    else:
        with_id = result.iloc[0:0].copy()
        without_id = result

    if not without_id.empty:
        geometry_key = without_id.geometry.to_wkb(hex=True)
        without_id = without_id.loc[~geometry_key.duplicated()].copy()
    combined = pd.concat([with_id, without_id], ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=result.crs)


# --- Local regional extract backend -----------------------------------------
#
# Overpass tiling exists only because the public API rejects large queries
# (see GREEN_TAG_MAX_TILE_SPAN_DEG). A local Geofabrik `.osm.pbf` has no such
# limit: measured 2026-08-10 on cataluna-260809.osm.pbf, one filtered pass
# returns every feature the four tag-based layers need in ~3 min, against the
# ~69 h that greenspace_access alone costs over Overpass for the same region.
#
# GDAL's OSM driver promotes a fixed set of keys to real columns per layer and
# leaves everything else in an hstore-style `other_tags` string. Both routes
# are supported so callers keep passing the same tag dict they pass Overpass.

_OSM_PROMOTED_FIELDS: dict[str, frozenset[str]] = {
    # Verified with pyogrio.read_info() against a real extract; these are
    # GDAL's stock osmconf.ini attributes, not a guess.
    "multipolygons": frozenset(
        {
            "name", "type", "aeroway", "amenity", "admin_level", "barrier",
            "boundary", "building", "craft", "geological", "historic",
            "land_area", "landuse", "leisure", "man_made", "military",
            "natural", "office", "place", "shop", "sport", "tourism",
        }
    ),
    "points": frozenset(
        {"name", "barrier", "highway", "ref", "address", "is_in", "place", "man_made"}
    ),
}

_ELEMENT_BY_LAYER = {"points": "node", "lines": "way", "multipolygons": "way"}


def parse_other_tags(value: Any) -> dict[str, str]:
    """Parse GDAL's ``other_tags`` hstore string into a plain dict.

    Format is ``"key"=>"value","key2"=>"value2"``; quotes inside a value are
    backslash-escaped. Malformed fragments are skipped rather than raising --
    a single odd tag must not lose an entire region's features.

    Limitation: an *unbalanced* quote inverts the quoting state and
    desynchronises the rest of the string, so pairs after it come back as junk
    keys instead of being skipped. That still beats raising (the layer would
    lose the whole region) and is harmless downstream, because a junk key
    matches none of the keys the caller asked to materialize.
    """
    if not isinstance(value, str) or not value:
        return {}
    tags: dict[str, str] = {}
    key: list[str] = []
    val: list[str] = []
    target = key
    in_quotes = False
    escaped = False
    seen_arrow = False
    for index, char in enumerate(value):
        if escaped:
            target.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            target.append(char)
            continue
        if char == "=" and value[index + 1 : index + 2] == ">":
            target = val
            seen_arrow = True
            continue
        if char == ">" and seen_arrow and not val:
            continue
        if char == ",":
            if key:
                tags["".join(key)] = "".join(val)
            key, val = [], []
            target = key
            seen_arrow = False
    if key:
        tags["".join(key)] = "".join(val)
    return tags


def _sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def local_extract_where(tags: dict[str, Any], layer: str) -> str:
    """Build the OGR SQL ``where`` that selects ``tags`` inside ``layer``.

    Promoted keys use an indexable ``IN`` test; everything else falls back to
    a ``LIKE`` over ``other_tags``. Returns ``""`` when no clause applies, so
    callers can skip the layer entirely instead of scanning it for nothing.
    """
    promoted = _OSM_PROMOTED_FIELDS.get(layer, frozenset())
    clauses: list[str] = []
    for key, values in tags.items():
        if values is True or values is None:
            candidates: list[str] = []
        elif isinstance(values, str):
            candidates = [values]
        else:
            candidates = [str(item) for item in values]
        if key in promoted:
            if candidates:
                joined = ",".join(_sql_quote(item) for item in candidates)
                clauses.append(f"{key} IN ({joined})")
            else:
                clauses.append(f"{key} IS NOT NULL")
        else:
            for item in candidates:
                escaped = str(item).replace("'", "''")
                clauses.append(f"other_tags LIKE '%\"{key}\"=>\"{escaped}\"%'")
            if not candidates:
                clauses.append(f"other_tags LIKE '%\"{key}\"=>%'")
    return " OR ".join(clauses)


def fetch_features_from_local_extract(
    extract_path: str | Path,
    tags: dict[str, Any],
    *,
    label: str,
    layers: Sequence[str] = ("multipolygons", "points"),
    extra_keys: Sequence[str] = (),
    log: Callable[[str], None] = print,
) -> gpd.GeoDataFrame:
    """Read tagged OSM features from a local ``.osm.pbf``.

    Returns the same frame contract as :func:`fetch_features_from_bbox_tiled`
    (``element``/``id``/``name``/one column per requested tag key/``geometry``)
    so callers cannot tell which backend produced it.

    ``extra_keys`` names tags to *materialize as columns without filtering on
    them*. Overpass hands back every tag a feature carries, so callers can read
    a column they never queried; here only the requested keys exist unless they
    are asked for. ``social_infrastructure`` depends on this: it filters on
    ``access`` (private/customers/no/permit) but never queries it, and a missing
    column silently admits every excluded venue.
    """
    path = Path(extract_path)
    if not path.exists():
        raise FileNotFoundError(f"OSM extract not found for {label}: {path}")

    pieces: list[gpd.GeoDataFrame] = []
    tag_keys = list(tags)
    # Filtering is driven by `tags` alone; `extra_keys` only widens the columns.
    all_keys = tag_keys + [key for key in extra_keys if key not in tags]
    for layer in layers:
        where = local_extract_where(tags, layer)
        if not where:
            continue
        promoted = _OSM_PROMOTED_FIELDS.get(layer, frozenset())
        columns = ["osm_id", "name"]
        if layer == "multipolygons":
            columns.append("osm_way_id")
        columns.extend(key for key in all_keys if key in promoted)
        if any(key not in promoted for key in all_keys):
            columns.append("other_tags")
        log(f"  [{label}] reading {layer} from {path.name}")
        frame = gpd.read_file(
            path, layer=layer, where=where, columns=sorted(set(columns)), engine="pyogrio"
        )
        if frame.empty:
            continue

        # A closed way carries osm_way_id; a multipolygon relation carries
        # osm_id. Keeping them apart matters because the two id spaces overlap
        # and _deduplicate_osm_features keys on (element, id).
        if layer == "multipolygons" and "osm_way_id" in frame.columns:
            is_way = frame["osm_way_id"].notna()
            frame["element"] = pd.Series("relation", index=frame.index).mask(is_way, "way")
            frame["id"] = frame["osm_id"].mask(is_way, frame["osm_way_id"])
            frame = frame.drop(columns=["osm_way_id"])
        else:
            frame["element"] = _ELEMENT_BY_LAYER.get(layer, "way")
            frame["id"] = frame["osm_id"]
        frame = frame.drop(columns=["osm_id"])

        if "other_tags" in frame.columns:
            parsed = frame["other_tags"].map(parse_other_tags)
            for key in all_keys:
                if key in promoted:
                    continue
                frame[key] = parsed.map(lambda item, key=key: item.get(key))
            frame = frame.drop(columns=["other_tags"])
        for key in all_keys:
            if key not in frame.columns:
                frame[key] = None
        pieces.append(frame)
        log(f"  [{label}] {layer}: {len(frame):,} features")

    if not pieces:
        # Carry the full column contract even with no rows: callers reach for
        # these columns with .get(), and a missing one degrades silently.
        empty = {key: [] for key in ("element", "id", "name", *all_keys)}
        return gpd.GeoDataFrame({**empty, "geometry": []}, crs="EPSG:4326")
    combined = gpd.GeoDataFrame(
        pd.concat(pieces, ignore_index=True), geometry="geometry", crs=pieces[0].crs
    )
    return _deduplicate_osm_features(combined)


def fetch_features_from_bbox_tiled(
    bbox: Sequence[float],
    tags: dict[str, Any],
    *,
    label: str,
    grid_size: int = 1,
    between_tiles_s: float = 2.0,
    checkpoint_dir: Path | None = None,
    attempts: int = 2,
    attempt_timeout_s: float | None = 180.0,
    log: Callable[[str], None] = print,
) -> gpd.GeoDataFrame:
    """Fetch OSM features over a bbox using small, checkpoint-friendly queries.

    Administrative place-name lookups are both ambiguous and expensive: the
    failing Lima/Bogota/Sao Paulo runs repeatedly spent hours asking Nominatim
    to resolve the same locality before Overpass could even run.  Callers that
    already own authoritative study polygons should query their bbox instead.
    Large bboxes can be split into ``grid_size ** 2`` tiles; overlapping OSM
    features are deduplicated by their stable ``element/id`` pair.
    """
    tiles = _bbox_tiles(bbox, grid_size)
    query_cache = None
    if checkpoint_dir is not None:
        query_key = _tile_query_key(bbox, tags, grid_size)
        query_cache = Path(checkpoint_dir) / f"query_{query_key}"
        query_cache.mkdir(parents=True, exist_ok=True)
        manifest = query_cache / "manifest.json"
        if not manifest.exists():
            _write_json_atomic(
                {
                    "schema_version": 1,
                    "query_key": query_key,
                    "bbox": [float(value) for value in bbox],
                    "tags": tags,
                    "grid_size": int(grid_size),
                    "tiles": len(tiles),
                },
                manifest,
            )

    pieces: list[gpd.GeoDataFrame] = []
    failed_tiles: list[int] = []
    for index, tile in enumerate(tiles, start=1):
        tile_label = label if len(tiles) == 1 else f"{label} tile {index}/{len(tiles)}"
        tile_cache = (
            query_cache / f"tile_{index:04d}_of_{len(tiles):04d}.geojson"
            if query_cache is not None
            else None
        )
        if tile_cache is not None and tile_cache.exists():
            log(f"  [{tile_label}] loading tile checkpoint")
            piece = gpd.read_file(tile_cache)
            if not piece.empty:
                pieces.append(piece)
            continue

        log(f"  [{tile_label}] fetching from OSM")

        def query(current_tile: tuple[float, float, float, float] = tile) -> gpd.GeoDataFrame:
            # osmnx raises instead of returning empty when a tile has zero
            # matching features (routine for rural/sparse tiles, e.g. Bogota's
            # Usme/Sumapaz paramo) -- treat that as a real empty result, not a
            # connectivity failure to retry across mirrors.
            try:
                result = ox.features_from_bbox(current_tile, tags=tags)
            except InsufficientResponseError:
                return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
            if result is None or len(result) == 0:
                return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
            return _reset_osm_index(result)

        try:
            piece = call_with_overpass_fallback(
                query,
                label=tile_label,
                log=log,
                attempts=attempts,
                attempt_timeout_s=attempt_timeout_s,
            )
        except ConnectionError:
            # One stubborn tile shouldn't discard a whole run's progress: keep
            # going so a single invocation checkpoints every tile it can reach
            # (observed on Bogota's Usme/Sumapaz -- consecutive runs each only
            # got one tile further before dying on the next untried one). Only
            # the tiles still missing afterwards need a future --resume.
            log(f"  [{tile_label}] FAILED, skipping for now")
            failed_tiles.append(index)
            if index < len(tiles) and between_tiles_s > 0:
                time.sleep(between_tiles_s)
            continue
        if tile_cache is not None:
            _write_geojson_atomic(piece, tile_cache)
        if not piece.empty:
            pieces.append(piece)
        if index < len(tiles) and between_tiles_s > 0:
            time.sleep(between_tiles_s)

    if failed_tiles:
        raise ConnectionError(
            f"Failed to download {len(failed_tiles)} of {len(tiles)} tile(s) for "
            f"{label}: {failed_tiles}. Already-fetched tiles are cached under "
            f"{query_cache}; re-run with --resume to retry only the missing ones."
        )

    if not pieces:
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    combined = gpd.GeoDataFrame(
        pd.concat(pieces, ignore_index=True),
        geometry="geometry",
        crs=pieces[0].crs,
    )
    return _deduplicate_osm_features(combined)
