"""Fetch ECOSTRESS land surface temperature (LST) from NASA Earthdata.

Earth Engine hosts ``ECO_L2T_LSTE`` but has only ingested tiles over the Los
Angeles metro area, so no Latin American city can be served from it.  This
module goes to NASA Earthdata directly (CMR search + cloud GeoTIFF reads) and
is the only provider in the pipeline that does not go through GEE.

Why this layer exists, and what it is not
-----------------------------------------
``climate_heat`` publishes ERA5-Land 2 m **air** temperature at 11132 m.
ECOSTRESS publishes radiative **skin** temperature at 70 m.  These are
different physical quantities -- during the day LST runs well above T2M over
built surfaces -- so this layer complements ``climate_heat`` and never
replaces it.

The scientific value that no sun-synchronous sensor can match is the
International Space Station's precessing orbit: acquisitions land at varying
local solar hours, so the diurnal cycle can be characterised.  MODIS is fixed
at 10:30/13:30 and Landsat at ~10:00.  Every reduction here is therefore
binned by local solar hour rather than averaged over the whole day.

Design constraints that drove this implementation
-------------------------------------------------
A study is not a city block.  ``santiago_communes`` spans 180 x 151 km (the
whole Region Metropolitana), which is ~12 MGRS tiles across **two UTM zones**
(18 and 19), and roughly 400 granules per month.  Caching per-granule crops
would run to hundreds of GB inside a Dropbox-synced repo, so instead:

* granules are streamed and reduced on the fly into fixed study-grid
  accumulators (sum / count / max per solar-hour bin), checkpointed as ``.npz``
  so a run resumes without re-downloading;
* per-pixel percentiles are deliberately not accumulated -- they would need
  per-pixel histograms (~TB at this grid size).  Percentiles are computed
  across pixels within a spatial unit at aggregation time, from the composite,
  which is also the standard way surface-UHI statistics are reported;
* a small per-granule, per-unit summary row is cached alongside so the
  observation-level record survives and the tabular product can be redefined
  without re-downloading anything.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

SHORT_NAME = "ECO_L2T_LSTE"
DEFAULT_VERSION = "002"  # v003 is not backfilled before 2025; see config/layers/climate_lst_ecostress.yaml

# ECOSTRESS L2T LSTE stores LST as scaled unsigned integers in Kelvin.
# The scale is carried in the GeoTIFF metadata; this is the documented
# fallback when a granule omits it.
LST_SCALE = 0.02
LST_FILL = 0
KELVIN_OFFSET = 273.15

# Physically implausible skin temperatures indicate a bad retrieval that the
# QC bits did not catch.  Values outside this range are dropped.
LST_MIN_C = -50.0
LST_MAX_C = 80.0

GRANULE_ID_RE = re.compile(
    r"ECOv\d+_L2T_LSTE_(?P<orbit>\d+)_(?P<scene>\d+)_"
    r"(?P<tile>\d{2}[A-Z]{3})_(?P<stamp>\d{8}T\d{6})_"
)


@dataclass(frozen=True)
class SolarWindow:
    """A named range of local solar hours, half-open on the right.

    Windows may wrap past midnight (``start > end``), which is how the night
    window is expressed.
    """

    name: str
    start: float
    end: float

    def contains(self, hour: float) -> bool:
        if self.start <= self.end:
            return self.start <= hour < self.end
        return hour >= self.start or hour < self.end


# Daytime covers the surface-UHI maximum; night covers the nocturnal UHI,
# which is the stronger and more socially patterned signal in the Santiago
# literature.  Hours between the two are collected but not reduced, because a
# transition-hour mean mixes heating and cooling regimes.
DEFAULT_WINDOWS: tuple[SolarWindow, ...] = (
    SolarWindow("day", 10.0, 16.0),
    SolarWindow("night", 22.0, 5.0),
)


def local_solar_hour(when: datetime, longitude: float) -> float:
    """Return the mean local solar hour for a UTC instant at a longitude.

    Uses the longitude offset rather than the civil timezone on purpose: the
    diurnal binning is about sun position, not about clocks or daylight saving.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    utc = when.astimezone(timezone.utc)
    hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    return (hour + longitude / 15.0) % 24.0


def window_for_hour(
    hour: float, windows: Sequence[SolarWindow] = DEFAULT_WINDOWS
) -> str | None:
    """Return the name of the first window containing ``hour``, else None."""
    for window in windows:
        if window.contains(hour):
            return window.name
    return None


def parse_granule_id(granule_id: str) -> dict[str, Any]:
    """Extract tile and acquisition time from an ECOSTRESS L2T granule name.

    Granule ids look like
    ``ECOv002_L2T_LSTE_26543_007_19HCC_20230115T143052_0712_01``.
    """
    match = GRANULE_ID_RE.search(granule_id)
    if match is None:
        raise ValueError(f"Unrecognised ECOSTRESS L2T granule id: {granule_id!r}")
    stamp = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%S").replace(
        tzinfo=timezone.utc
    )
    return {
        "orbit": match.group("orbit"),
        "scene": match.group("scene"),
        "tile": match.group("tile"),
        "acquired_utc": stamp,
    }


def decode_lst(
    raw: np.ndarray,
    *,
    scale: float = LST_SCALE,
    offset: float = 0.0,
    fill: int = LST_FILL,
) -> np.ndarray:
    """Convert packed LST digital numbers to Celsius, fill values -> NaN."""
    values = raw.astype("float32")
    values[raw == fill] = np.nan
    return values * scale + offset - KELVIN_OFFSET


def quality_mask(
    *,
    lst_c: np.ndarray,
    cloud: np.ndarray | None = None,
    water: np.ndarray | None = None,
    qc: np.ndarray | None = None,
    max_qc_level: int = 1,
) -> np.ndarray:
    """Return a boolean mask of pixels safe to use.

    Drops fill/NaN, cloud, water, out-of-range retrievals, and -- when a QC
    band is supplied -- pixels whose mandatory quality-flag bits (0-1) exceed
    ``max_qc_level`` (0 = best, 1 = nominal).
    """
    keep = np.isfinite(lst_c)
    keep &= (lst_c >= LST_MIN_C) & (lst_c <= LST_MAX_C)
    if cloud is not None:
        keep &= cloud == 0
    if water is not None:
        keep &= water == 0
    if qc is not None:
        keep &= (qc & 0b11) <= max_qc_level
    return keep


@dataclass
class WindowAccumulator:
    """Streaming per-pixel sum/count/max on a fixed grid for one solar window.

    Percentiles are intentionally absent -- see the module docstring.
    """

    shape: tuple[int, int]
    total: np.ndarray = field(init=False)
    count: np.ndarray = field(init=False)
    maximum: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.total = np.zeros(self.shape, dtype="float64")
        self.count = np.zeros(self.shape, dtype="uint32")
        self.maximum = np.full(self.shape, -np.inf, dtype="float32")

    def update(self, values: np.ndarray, mask: np.ndarray) -> int:
        """Fold one granule's reprojected values in. Returns pixels added."""
        if values.shape != self.shape or mask.shape != self.shape:
            raise ValueError(
                f"Granule grid {values.shape} does not match accumulator {self.shape}"
            )
        safe = np.where(mask, values, 0.0).astype("float64")
        self.total += safe
        self.count += mask.astype("uint32")
        np.maximum(self.maximum, np.where(mask, values, -np.inf), out=self.maximum)
        return int(mask.sum())

    def mean(self) -> np.ndarray:
        """Per-pixel mean; pixels never observed come back as NaN."""
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.where(self.count > 0, self.total / np.maximum(self.count, 1), np.nan)
        return out.astype("float32")

    def peak(self) -> np.ndarray:
        return np.where(self.count > 0, self.maximum, np.nan).astype("float32")

    def to_arrays(self, prefix: str) -> dict[str, np.ndarray]:
        return {
            f"{prefix}__total": self.total,
            f"{prefix}__count": self.count,
            f"{prefix}__maximum": self.maximum,
        }

    @classmethod
    def from_arrays(cls, prefix: str, payload: Mapping[str, np.ndarray]) -> "WindowAccumulator":
        total = np.asarray(payload[f"{prefix}__total"])
        acc = cls(shape=total.shape)
        acc.total = total.astype("float64")
        acc.count = np.asarray(payload[f"{prefix}__count"]).astype("uint32")
        acc.maximum = np.asarray(payload[f"{prefix}__maximum"]).astype("float32")
        return acc


class AccumulatorSet:
    """One :class:`WindowAccumulator` per solar window, plus resume state."""

    def __init__(
        self,
        shape: tuple[int, int],
        windows: Sequence[SolarWindow] = DEFAULT_WINDOWS,
    ) -> None:
        self.shape = shape
        self.windows = tuple(windows)
        self.accumulators = {w.name: WindowAccumulator(shape=shape) for w in self.windows}
        self.processed: set[str] = set()

    def update(self, window_name: str, values: np.ndarray, mask: np.ndarray) -> int:
        return self.accumulators[window_name].update(values, mask)

    def mark_processed(self, granule_id: str) -> None:
        self.processed.add(granule_id)

    def save(self, path: Path) -> Path:
        """Checkpoint atomically so an interrupted write cannot poison a resume."""
        payload: dict[str, Any] = {}
        for name, acc in self.accumulators.items():
            payload.update(acc.to_arrays(name))
        payload["__windows__"] = np.array(
            [(w.name, w.start, w.end) for w in self.windows], dtype=object
        )
        payload["__processed__"] = np.array(sorted(self.processed), dtype=object)
        path.parent.mkdir(parents=True, exist_ok=True)
        # The temp name must itself end in .npz: savez_compressed silently
        # appends the extension otherwise, and the atomic rename would then
        # look for a file numpy never wrote -- losing every checkpoint of a
        # multi-hour run at the first save.
        tmp = path.with_name(f".{path.stem}.tmp.npz")
        np.savez_compressed(tmp, **payload)
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: Path) -> "AccumulatorSet":
        with np.load(path, allow_pickle=True) as data:
            payload = {key: data[key] for key in data.files}
        windows = tuple(
            SolarWindow(str(name), float(start), float(end))
            for name, start, end in payload["__windows__"]
        )
        first = np.asarray(payload[f"{windows[0].name}__total"])
        out = cls(shape=first.shape, windows=windows)
        out.accumulators = {
            w.name: WindowAccumulator.from_arrays(w.name, payload) for w in windows
        }
        out.processed = {str(item) for item in payload["__processed__"]}
        return out


AUTH_HINT = (
    "NASA Earthdata authentication required. earthaccess ships no CLI, so there "
    "is no `earthaccess login` command. Run once:\n"
    "    .venv/bin/python -c \"import earthaccess; "
    "earthaccess.login(strategy='interactive', persist=True)\"\n"
    "Free account: https://urs.earthdata.nasa.gov  "
    "(EARTHDATA_USERNAME/EARTHDATA_PASSWORD or EARTHDATA_TOKEN also work.)"
)


def ensure_earthdata_auth() -> Any:
    """Authenticate against Earthdata, failing with an actionable message.

    Called before any download so a missing credential surfaces immediately
    instead of hundreds of granules into an overnight run.

    Only the non-interactive strategies are attempted, deliberately.
    ``strategy="all"`` falls through to ``"interactive"``, which *prompts on
    stdin* -- an unattended overnight run would hang there forever instead of
    failing fast.  The interactive login is a separate, human-run step.
    """
    import earthaccess

    for strategy in ("environment", "netrc"):
        try:
            auth = earthaccess.login(strategy=strategy, persist=False)
        except Exception:  # noqa: BLE001 - try the next strategy
            continue
        if getattr(auth, "authenticated", False):
            return auth
    raise RuntimeError(AUTH_HINT)


def search_granules(
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    version: str = DEFAULT_VERSION,
    short_name: str = SHORT_NAME,
) -> list[Any]:
    """Search NASA CMR for L2T LSTE granules intersecting ``bbox``.

    ``bbox`` is (west, south, east, north).  Requires a prior
    ``earthaccess.login()``; the import is deferred so this module stays
    importable, and unit-testable, without the dependency or a network.
    """
    import earthaccess

    return list(
        earthaccess.search_data(
            short_name=short_name,
            version=version,
            bounding_box=bbox,
            temporal=(start, end),
        )
    )


def granule_asset_urls(granule: Any) -> dict[str, str]:
    """Map band name -> URL for one granule's GeoTIFF assets.

    L2T granules ship one COG per band (``..._LST.tif``, ``..._cloud.tif``,
    ``..._water.tif``, ``..._QC.tif``, ...).
    """
    urls: dict[str, str] = {}
    for link in granule.data_links():
        if not link.endswith(".tif"):
            continue
        band = Path(link).stem.rsplit("_", 1)[-1]
        urls[band] = link
    return urls


def granule_native_id(granule: Any) -> str:
    """Best-effort native id for a granule, tolerant of shape differences."""
    if isinstance(granule, Mapping):
        meta = granule.get("meta") or {}
        native = meta.get("native-id") or meta.get("concept-id")
        if native:
            return str(native)
        umm = granule.get("umm") or {}
        if umm.get("GranuleUR"):
            return str(umm["GranuleUR"])
    return str(granule)


def iter_granule_windows(
    granules: Iterable[Any],
    longitude: float,
    windows: Sequence[SolarWindow] = DEFAULT_WINDOWS,
    *,
    skip: Iterable[str] = (),
) -> Iterator[tuple[Any, dict[str, Any]]]:
    """Yield (granule, info) for granules landing inside a solar window.

    ``longitude`` is the study's representative longitude, deliberately not the
    per-granule centroid: a study spanning several MGRS tiles must bin every
    tile of one overpass into the same solar window, otherwise the mosaic would
    be stitched from different diurnal regimes.

    Granules already in ``skip``, and granules acquired between the configured
    windows, are dropped here -- before any download.  That is what makes a
    resumed run cheap and keeps transition hours out of the composites.
    """
    seen = set(skip)
    for granule in granules:
        granule_id = granule_native_id(granule)
        if granule_id in seen:
            continue
        try:
            info = parse_granule_id(granule_id)
        except ValueError:
            continue
        hour = local_solar_hour(info["acquired_utc"], longitude)
        window = window_for_hour(hour, windows)
        if window is None:
            continue
        info["granule_id"] = granule_id
        info["solar_hour"] = hour
        info["window"] = window
        yield granule, info


@dataclass(frozen=True)
class StudyGrid:
    """The fixed target grid every granule is reprojected onto.

    Held in the study's metric CRS at the product's native 70 m.  Granules
    arrive on MGRS tiles that can sit in different UTM zones (Santiago spans
    zones 18 and 19), so a single common grid is the only way to accumulate
    them coherently.  Reprojection here preserves 70 m -- it never coarsens the
    product, which CLAUDE.md's max-resolution policy forbids.
    """

    crs: str
    transform: Any
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)


def build_study_grid(
    bounds: tuple[float, float, float, float],
    crs: str,
    resolution: float = 70.0,
) -> StudyGrid:
    """Build a 70 m grid covering ``bounds`` (in ``crs`` units), snapped out."""
    from rasterio.transform import from_origin

    west, south, east, north = bounds
    west = np.floor(west / resolution) * resolution
    south = np.floor(south / resolution) * resolution
    east = np.ceil(east / resolution) * resolution
    north = np.ceil(north / resolution) * resolution
    width = int(round((east - west) / resolution))
    height = int(round((north - south) / resolution))
    return StudyGrid(
        crs=crs,
        transform=from_origin(west, north, resolution, resolution),
        width=width,
        height=height,
    )


def reproject_to_grid(
    source: np.ndarray,
    src_transform: Any,
    src_crs: Any,
    grid: StudyGrid,
    *,
    nodata: float = np.nan,
) -> np.ndarray:
    """Reproject one granule band onto the study grid with nearest neighbour.

    Nearest is deliberate: LST is a masked, discontinuous field once cloud and
    water are removed, and bilinear would smear masked edges into valid pixels.
    """
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    destination = np.full(grid.shape, nodata, dtype="float32")
    reproject(
        source=source,
        destination=destination,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=nodata,
        dst_transform=grid.transform,
        dst_crs=grid.crs,
        dst_nodata=nodata,
        resampling=Resampling.nearest,
    )
    return destination


def resolve_lst_scaling(dtype: Any, scales: Sequence[float] | None) -> tuple[float, float]:
    """Return (scale, offset) for an LST band.

    Discriminating on dtype rather than on the declared scale is deliberate:
    rasterio reports ``scales == (1.0,)`` both when a file stores unscaled
    values and when it simply omits the tag, so trusting that value would
    silently leave packed Kelvin unscaled -- an error that looks like a
    plausible temperature field rather than like a crash.  Integer storage
    means packed; floating point means the values are already Kelvin.
    """
    if np.issubdtype(np.dtype(dtype), np.integer):
        if scales and scales[0] not in (0.0, 1.0):
            return float(scales[0]), 0.0
        return LST_SCALE, 0.0
    return 1.0, 0.0


def _earthdata_dataset(url: str) -> Any:
    """Open a remote ECOSTRESS COG through an authenticated Earthdata session."""
    import earthaccess
    import rasterio

    return rasterio.open(earthaccess.open([url])[0])


def read_granule_to_grid(
    urls: Mapping[str, str],
    grid: StudyGrid,
    *,
    max_qc_level: int = 1,
    opener: Any = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Read one granule, mask it, and reproject onto the study grid.

    Returns ``(values_celsius, mask)`` both shaped like the grid.  Ancillary
    bands are optional: a granule missing ``cloud`` still yields data, just
    with a weaker mask, which is preferable to dropping the acquisition.
    """
    open_dataset = opener or _earthdata_dataset
    if "LST" not in urls:
        raise KeyError(f"Granule has no LST band; got {sorted(urls)}")

    with open_dataset(urls["LST"]) as src:
        raw = src.read(1)
        src_transform, src_crs = src.transform, src.crs
        scale, offset = resolve_lst_scaling(raw.dtype, src.scales)
    lst_c = decode_lst(raw, scale=scale, offset=offset)

    ancillary: dict[str, np.ndarray | None] = {"cloud": None, "water": None, "QC": None}
    for band in ancillary:
        if band not in urls:
            continue
        with open_dataset(urls[band]) as src:
            ancillary[band] = src.read(1)

    keep = quality_mask(
        lst_c=lst_c,
        cloud=ancillary["cloud"],
        water=ancillary["water"],
        qc=ancillary["QC"],
        max_qc_level=max_qc_level,
    )
    masked = np.where(keep, lst_c, np.nan).astype("float32")
    projected = reproject_to_grid(masked, src_transform, src_crs, grid)
    return projected, np.isfinite(projected)


def write_composite(
    path: Path,
    bands: Mapping[str, np.ndarray],
    grid: StudyGrid,
    *,
    descriptions: Mapping[str, str] | None = None,
) -> Path:
    """Write the reduced composite as a tiled, compressed COG."""
    import rasterio

    names = list(bands)
    if not names:
        raise ValueError("No bands to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": len(names),
        "dtype": "float32",
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": np.nan,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
        "predictor": 3,
        "BIGTIFF": "IF_SAFER",
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with rasterio.open(tmp, "w", **profile) as dst:
        for index, name in enumerate(names, start=1):
            dst.write(bands[name].astype("float32"), index)
            dst.set_band_description(index, (descriptions or {}).get(name, name))
        dst.build_overviews([2, 4, 8, 16], rasterio.enums.Resampling.average)
    tmp.replace(path)
    return path
