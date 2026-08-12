"""Cross-city distribution comparison: robust scale, histograms, eCDFs, tests.

Pure functions with no I/O: they take numpy arrays already extracted from a
master table or a native raster, and return JSON-serializable dictionaries
(``float``/``int`` native types, never ``numpy`` scalars). The caller
(``scripts/export_webapp_distributions.py``) owns all file access.

Methodology
-----------
- Robust scale via the asymmetric ("double") MAD: the median absolute
  deviation is computed separately below and above the median (Rosenmai
  2013), because most exposome indicators are right-skewed and a single
  symmetric MAD both underestimates the upper tail and can push the lower
  fence below a physical floor (e.g. a concentration cannot be negative).
  ``sigma = 1.4826 * MAD`` is the standard consistency-corrected scale
  estimator for normally-distributed data (Leys et al. 2013).
- KS and Anderson-Darling (k-sample, Scholz & Stephens 1987) are computed via
  scipy rather than reimplemented, because the AD critical-value
  interpolation with tie correction is easy to get subtly wrong; scipy also
  caps/floors the reported p-value honestly instead of underflowing to 0 on
  large samples.
- With thousands of spatially autocorrelated grid pixels, standard p-values
  collapse to ~0 regardless of the real difference between cities (the
  "large-n problem"). The statistic itself (KS D, bounded in [0, 1]; AD A2)
  is the effect size and should be read first; the p-value is secondary and
  flagged as unreliable at fine-grid sample sizes by the caller.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

MAD_CONSISTENCY_CONSTANT = 1.4826
OUTLIER_Z_THRESHOLD = 3.0
IQR_CONSISTENCY_CONSTANT = 1.349
# scipy.stats.anderson_ksamp raises a UserWarning and clips the reported
# p-value outside this range rather than extrapolating past its table.
_AD_P_TABLE_RANGE = (0.001, 0.25)
# Below this many points per city, ks_2samp's asymptotic method is not
# appropriate; scipy switches to the exact method automatically for small n
# via method="auto", which we rely on rather than hardcoding a threshold.
FINE_SAMPLE_AUTOCORR_WARNING_N = 2000


@dataclass(frozen=True)
class RobustScale:
    median: float
    mad_lower: float
    mad_upper: float
    sigma_lower: float
    sigma_upper: float
    band_low: float
    band_high: float
    scale_undefined_lower: bool
    scale_undefined_upper: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "median": self.median,
            "mad_lower": self.mad_lower,
            "mad_upper": self.mad_upper,
            "sigma_lower": self.sigma_lower,
            "sigma_upper": self.sigma_upper,
            "band_low": self.band_low,
            "band_high": self.band_high,
            "scale_undefined": bool(self.scale_undefined_lower or self.scale_undefined_upper),
            "scale_undefined_lower": self.scale_undefined_lower,
            "scale_undefined_upper": self.scale_undefined_upper,
        }


@dataclass(frozen=True)
class HistogramResult:
    bins: list[float]
    display_range: tuple[float, float]
    density_by_city: dict[str, list[float]]
    overflow_low_by_city: dict[str, int]
    overflow_high_by_city: dict[str, int]

    def to_json(self) -> dict[str, Any]:
        return {
            "bins": self.bins,
            "display_range": list(self.display_range),
            "density_by_city": self.density_by_city,
            "overflow_low_by_city": self.overflow_low_by_city,
            "overflow_high_by_city": self.overflow_high_by_city,
        }


@dataclass(frozen=True)
class LogHistogramResult:
    """Shared log10-spaced histogram, for the panel's optional log x-axis.

    Bin edges are returned in *linear* space (actual data values, all > 0), so
    the panel can position them on a log axis by taking ``log10`` -- the same
    ``bins`` shape as the linear :class:`HistogramResult`. Densities are per
    ``log10`` unit (constant pixel width on a log axis).
    """

    bins: list[float]
    density_by_city: dict[str, list[float]]
    n_nonpositive_by_city: dict[str, int]

    def to_json(self) -> dict[str, Any]:
        return {
            "bins": self.bins,
            "density_by_city": self.density_by_city,
            "n_nonpositive_by_city": self.n_nonpositive_by_city,
        }


@dataclass(frozen=True)
class EcdfResult:
    x: list[float]
    y: list[float]

    def to_json(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class KsResult:
    d: float
    p: float

    def to_json(self) -> dict[str, Any]:
        return {"d": self.d, "p": self.p}


@dataclass(frozen=True)
class AdResult:
    a2: float
    p: float
    p_capped: bool
    # Which end of scipy's significance table the p-value was clipped to, if
    # any: "floor" (p<=0.001, distributions clearly different), "ceiling"
    # (p>=0.25, indistinguishable by this test), or None (interpolated inside
    # the table). The two ends mean opposite things, so the renderer must not
    # collapse them into a single "capped" case.
    p_cap_side: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "a2": self.a2,
            "p": self.p,
            "p_capped": self.p_capped,
            "p_cap_side": self.p_cap_side,
        }


def _clean(values: np.ndarray) -> np.ndarray:
    """Drop NaN/inf. Callers are responsible for reporting how many were
    dropped (``n_dropped_nan``) before discarding that information here."""
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def robust_scale_double_mad(
    values: np.ndarray, *, physical_floor: float | None = 0.0
) -> RobustScale:
    """Asymmetric median +/- 3*sigma_hat band (Rosenmai double-MAD).

    Falls back to IQR/1.349 on whichever side has MAD == 0 (more than half
    the values on that side identical to the median -- common for
    zero-inflated indicators like wildfire or food-insecurity counts). If the
    IQR-based fallback is *also* zero, that side's scale is left at 0 and
    flagged ``scale_undefined_*`` so the caller can skip drawing that half of
    the band instead of collapsing it to the median.
    """
    arr = _clean(values)
    if arr.size == 0:
        return RobustScale(
            median=float("nan"),
            mad_lower=0.0,
            mad_upper=0.0,
            sigma_lower=0.0,
            sigma_upper=0.0,
            band_low=float("nan"),
            band_high=float("nan"),
            scale_undefined_lower=True,
            scale_undefined_upper=True,
        )
    median = float(np.median(arr))
    lower = arr[arr <= median]
    upper = arr[arr >= median]

    mad_lower = float(np.median(median - lower)) if lower.size else 0.0
    mad_upper = float(np.median(upper - median)) if upper.size else 0.0
    sigma_lower = MAD_CONSISTENCY_CONSTANT * mad_lower
    sigma_upper = MAD_CONSISTENCY_CONSTANT * mad_upper

    undefined_lower = False
    undefined_upper = False
    if sigma_lower == 0.0:
        sigma_lower, undefined_lower = _iqr_fallback(arr, median, side="lower")
    if sigma_upper == 0.0:
        sigma_upper, undefined_upper = _iqr_fallback(arr, median, side="upper")

    band_low = median - OUTLIER_Z_THRESHOLD * sigma_lower
    band_high = median + OUTLIER_Z_THRESHOLD * sigma_upper
    if physical_floor is not None:
        band_low = max(band_low, physical_floor)

    return RobustScale(
        median=median,
        mad_lower=mad_lower,
        mad_upper=mad_upper,
        sigma_lower=sigma_lower,
        sigma_upper=sigma_upper,
        band_low=band_low,
        band_high=band_high,
        scale_undefined_lower=undefined_lower,
        scale_undefined_upper=undefined_upper,
    )


def _iqr_fallback(arr: np.ndarray, median: float, *, side: str) -> tuple[float, bool]:
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = float(q3 - q1)
    if iqr == 0.0:
        return 0.0, True
    # Half the IQR approximates one side's spread around the median for a
    # roughly symmetric middle 50%; consistent with 1.349 = z(0.75) - z(0.25).
    return (iqr / IQR_CONSISTENCY_CONSTANT) / 2.0, False


def count_outliers(values: np.ndarray, scale: RobustScale) -> int:
    """Count points with |asymmetric z| > 3. Informative only -- never used
    to filter the sample; "mostrar todo" means outliers are counted, not
    dropped."""
    arr = _clean(values)
    if arr.size == 0 or np.isnan(scale.median):
        return 0
    below = arr < scale.median
    z = np.zeros_like(arr)
    if scale.sigma_lower > 0:
        z[below] = (scale.median - arr[below]) / scale.sigma_lower
    if scale.sigma_upper > 0:
        z[~below] = (arr[~below] - scale.median) / scale.sigma_upper
    return int(np.sum(z > OUTLIER_Z_THRESHOLD))


def _freedman_diaconis_bin_count(arr: np.ndarray, lo: float, hi: float, max_bins: int) -> int:
    n = arr.size
    if n < 2 or hi <= lo:
        return 1
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr <= 0:
        return min(max_bins, max(1, int(np.sqrt(n))))
    width = 2 * iqr / (n ** (1 / 3))
    if width <= 0:
        return max_bins
    n_bins = int(np.ceil((hi - lo) / width))
    return max(1, min(max_bins, n_bins))


def shared_histogram(
    values_by_city: dict[str, np.ndarray],
    *,
    max_bins: int = 60,
    display_percentiles: tuple[float, float] = (0.5, 99.5),
) -> HistogramResult:
    """Shared bin edges across all cities, sized on the *pooled* sample via
    Freedman-Diaconis (capped at ``max_bins`` -- 78k ALAN pixels would
    otherwise produce thousands of bins).

    The display range is the pooled [0.5, 99.5] percentile band, widened to
    cover the union of every city's double-MAD band so the band lines are
    never clipped out of view. Nothing is discarded from the *statistics*:
    values outside the display range are still counted, just rolled into
    ``overflow_low``/``overflow_high`` per city instead of stretching the
    axis to the most extreme single point.
    """
    cleaned = {city: _clean(vals) for city, vals in values_by_city.items()}
    cleaned = {city: vals for city, vals in cleaned.items() if vals.size}
    if not cleaned:
        return HistogramResult(
            bins=[0.0, 1.0],
            display_range=(0.0, 1.0),
            density_by_city={},
            overflow_low_by_city={},
            overflow_high_by_city={},
        )

    pooled = np.concatenate(list(cleaned.values()))
    lo, hi = np.percentile(pooled, list(display_percentiles))

    scales = {city: robust_scale_double_mad(vals) for city, vals in cleaned.items()}
    for scale in scales.values():
        if not scale.scale_undefined_lower:
            lo = min(lo, scale.band_low)
        if not scale.scale_undefined_upper:
            hi = max(hi, scale.band_high)
    if hi <= lo:
        hi = lo + 1.0

    n_bins = _freedman_diaconis_bin_count(pooled, lo, hi, max_bins)
    bins = np.linspace(lo, hi, n_bins + 1)

    density_by_city: dict[str, list[float]] = {}
    overflow_low: dict[str, int] = {}
    overflow_high: dict[str, int] = {}
    for city, vals in cleaned.items():
        in_range = vals[(vals >= lo) & (vals <= hi)]
        counts, _ = np.histogram(in_range, bins=bins)
        bin_widths = np.diff(bins)
        total = vals.size
        density = counts / (total * bin_widths) if total else np.zeros_like(counts, dtype=float)
        density_by_city[city] = [float(v) for v in density]
        overflow_low[city] = int(np.sum(vals < lo))
        overflow_high[city] = int(np.sum(vals > hi))

    return HistogramResult(
        bins=[float(b) for b in bins],
        display_range=(float(lo), float(hi)),
        density_by_city=density_by_city,
        overflow_low_by_city=overflow_low,
        overflow_high_by_city=overflow_high,
    )


def shared_histogram_log(
    values_by_city: dict[str, np.ndarray],
    *,
    max_bins: int = 60,
) -> LogHistogramResult:
    """Shared ``log10``-spaced bin edges across all cities, for right-skewed
    indicators (ALAN, extreme precipitation) where a linear axis crushes the
    bulk of the mass into the leftmost bins.

    Only strictly-positive values enter -- ``log10`` is undefined at 0. The
    caller only requests this view when the pooled minimum is already > 0, so
    in practice nothing is dropped, but any non-positive values are counted in
    ``n_nonpositive_by_city`` for transparency. There is deliberately **no
    overflow bin**: log compression already keeps the tail on-scale, so the
    full positive range is shown. Density is per ``log10`` unit, so the bars
    have constant width on a log axis and integrate to ~1 there.
    """
    cleaned = {city: _clean(vals) for city, vals in values_by_city.items()}
    nonpos = {city: int(np.sum(vals <= 0)) for city, vals in cleaned.items()}
    positive = {city: vals[vals > 0] for city, vals in cleaned.items()}
    positive = {city: vals for city, vals in positive.items() if vals.size}
    if not positive:
        return LogHistogramResult(bins=[], density_by_city={}, n_nonpositive_by_city=nonpos)

    pooled_log = np.log10(np.concatenate(list(positive.values())))
    lo, hi = float(pooled_log.min()), float(pooled_log.max())
    if hi <= lo:
        hi = lo + 1.0
    n_bins = _freedman_diaconis_bin_count(pooled_log, lo, hi, max_bins)
    log_edges = np.linspace(lo, hi, n_bins + 1)
    bin_widths = np.diff(log_edges)

    density_by_city: dict[str, list[float]] = {}
    for city, vals in positive.items():
        counts, _ = np.histogram(np.log10(vals), bins=log_edges)
        density = counts / (vals.size * bin_widths)
        density_by_city[city] = [float(v) for v in density]

    return LogHistogramResult(
        bins=[float(10.0**e) for e in log_edges],
        density_by_city=density_by_city,
        n_nonpositive_by_city=nonpos,
    )


def ecdf_points(values: np.ndarray, *, max_points: int = 250) -> EcdfResult:
    """Step points of the full empirical CDF, subsampled to at most
    ``max_points`` while always preserving the first and last point (min and
    max of the sample) -- a blind uniform subsample could otherwise smear out
    the steepest jump, which is exactly where the KS statistic lives."""
    arr = np.sort(_clean(values))
    n = arr.size
    if n == 0:
        return EcdfResult(x=[], y=[])
    y_full = np.arange(1, n + 1) / n
    if n <= max_points:
        return EcdfResult(x=[float(v) for v in arr], y=[float(v) for v in y_full])
    idx = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    idx[0] = 0
    idx[-1] = n - 1
    return EcdfResult(x=[float(arr[i]) for i in idx], y=[float(y_full[i]) for i in idx])


def ks_two_sample(a: np.ndarray, b: np.ndarray) -> KsResult:
    """Wraps ``scipy.stats.ks_2samp`` with the asymptotic method (appropriate
    once either sample is reasonably large; scipy's ``method="auto"`` already
    picks the exact method for small n)."""
    arr_a, arr_b = _clean(a), _clean(b)
    if arr_a.size == 0 or arr_b.size == 0:
        return KsResult(d=float("nan"), p=float("nan"))
    result = stats.ks_2samp(arr_a, arr_b, method="auto")
    return KsResult(d=float(result.statistic), p=float(result.pvalue))


def ad_ksample(samples: list[np.ndarray]) -> AdResult | None:
    """Wraps ``scipy.stats.anderson_ksamp`` (Scholz & Stephens 1987, with tie
    correction). Returns ``None`` when fewer than two non-empty samples are
    given -- there is nothing to compare against a single city -- or when the
    pooled sample has fewer than 2 distinct values (a constant/near-constant
    admin column, e.g. a boolean flag identical across every unit in every
    city): scipy itself refuses to run the test on a degenerate sample like
    that, and there is genuinely no "shape difference" to test for.

    scipy clips the reported p-value to its significance-level table
    (~[0.001, 0.25]) rather than extrapolating; ``p_capped`` flags when that
    clipping happened, which is the honest behaviour on large fine-grid
    samples where every difference looks "significant".
    """
    cleaned = [_clean(s) for s in samples]
    cleaned = [s for s in cleaned if s.size > 0]
    if len(cleaned) < 2:
        return None
    if np.unique(np.concatenate(cleaned)).size < 2:
        return None
    # Default method=None floors/caps the p-value at 0.1%/25% against the
    # Scholz & Stephens table rather than extrapolating past it; scipy warns
    # every time that happens (expected and common here), so silence it --
    # we detect the same condition ourselves via _AD_P_TABLE_RANGE below.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        result = stats.anderson_ksamp(cleaned, variant="midrank")
    p = float(result.pvalue)
    if p <= _AD_P_TABLE_RANGE[0]:
        side: str | None = "floor"
    elif p >= _AD_P_TABLE_RANGE[1]:
        side = "ceiling"
    else:
        side = None
    return AdResult(a2=float(result.statistic), p=p, p_capped=side is not None, p_cap_side=side)
