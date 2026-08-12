// Read what a study publishes for an indicator, from its manifest.
//
// Deliberately dependency-free: the COG reader's ESM build uses extensionless
// imports that only a bundler resolves, so anything importing it is untestable
// under `node --test`. These helpers carry the honesty rules, so they are the
// part that most needs coverage.

// Never infer availability from palette.json's has_fine_layer: it flags four
// indicators when eleven have COGs, and one of those four (`green`) has no .tif
// at all — its detail is subcomuna/green.geojson (ADR 0012 §5).
export function detailAssetFor(manifest, indicatorId, year = null) {
  if (!manifest) return null;
  if (year === null || year === undefined) {
    return manifest.spatial_indicators?.[indicatorId]?.detail || null;
  }
  const years = manifest.temporal_indicators?.[indicatorId]?.years;
  return years?.[String(year)]?.detail || null;
}

// The study's own reason an indicator is unavailable, or null when it is
// available (ADR 0004 §11: country_not_supported, not_enabled_by_study,
// not_published_by_study, coming_soon).
export function unavailableReason(manifest, indicatorId) {
  const record = manifest?.spatial_indicators?.[indicatorId];
  if (!record) return "not_published_by_study";
  const availability = record.availability;
  if (!availability || !availability.status || availability.status === "available") {
    return null;
  }
  return availability.reason || availability.status;
}

// The repo's own convention: INDICATOR_SUPPORT declares a 0.01 degree grid as
// 1113.2 m, which is 0.01 * 111320.
const METRES_PER_DEGREE = 111320;

// Convert a declared resolution object to ground metres, taking the larger
// axis. Anisotropic footprints reduce to their longest dimension on purpose: a
// buffer that does not span the long axis of an observation has not averaged
// over an independent measurement. For NO2 that is 7000 m, not 3500 m.
export function resolutionMetres(resolution) {
  if (!resolution) return null;
  const unit = String(resolution.unit || "").toLowerCase();
  if (unit === "vector") return null;
  const candidates = [];
  for (const key of ["value", "x", "y", "y_max", "x_max"]) {
    const raw = resolution[key];
    if (raw !== null && raw !== undefined && Number.isFinite(Number(raw))) {
      candidates.push(Number(raw));
    }
  }
  if (!candidates.length) return null;
  const largest = Math.max(...candidates);
  // Longitude degrees shrink by cos(latitude); latitude degrees do not, so the
  // north-south extent bounds the cell and needs no latitude correction.
  return unit === "degree" ? largest * METRES_PER_DEGREE : largest;
}

// Ground metres of support, mirroring point_support.effective_support_m.
//
// Takes the coarsest of the observation footprint and the analysis grid,
// because neither dominates in general and the manifest's own
// `source_native_resolution_m` is wrong in both directions:
//
//   no2    declares 1113.0 but a TROPOMI observation covers 3.5 x 5.5-7 km
//   canopy declares 1.0 (the source canopy *height*) but publishes a canopy
//          *fraction* aggregated to 30 m
//
// Taking the maximum is the only choice that never overclaims. Note that
// `storage_grid.resolution` is never used: it is in Web Mercator units, which
// are not ground metres (Santiago PM2.5 stores 1192.4 for a 1113.0 m product).
export function effectiveSupportM(indicatorRecord) {
  if (!indicatorRecord) return null;
  const observation = resolutionMetres(indicatorRecord.observation?.resolution);
  const analysis = resolutionMetres(indicatorRecord.analysis?.resolution);
  const known = [observation, analysis].filter((value) => Number.isFinite(value));
  return known.length ? Math.max(...known) : null;
}

// The provider's nominal figure, for reporting alongside the support — never as
// the support itself.
export function sourceNativeResolutionM(asset) {
  const declared = asset?.source_native_resolution_m;
  return Number.isFinite(declared) ? Number(declared) : null;
}

// Whether a requested radius resolves anything, mirroring
// src/exposome/point_support.py::radius_status. The gate is the coarsest of the
// observation footprint and the analysis grid: NO2 is analysed on a 1113 m grid
// but observed over 3.5 x 5.5-7 km, while canopy is observed at 1 m but
// published aggregated to 30 m. Taking the maximum never overclaims.
export function radiusStatus(supportM, radiusM) {
  if (!Number.isFinite(supportM)) return "not_applicable";
  return 2 * Number(radiusM) >= supportM ? "resolved" : "sub_observation";
}

// The support actually delivered: never finer than the product allows.
export function deliveredSupportM(supportM, radiusM) {
  if (!Number.isFinite(supportM)) return null;
  return Math.max(2 * Number(radiusM), supportM);
}

// Under sub_observation every contributing cell sits inside one observation
// footprint, so the spread collapses toward zero and would read as high
// confidence exactly where the data is least informative (ADR 0012 §4).
export function emitsWithinBufferSd(supportM, radiusM) {
  return radiusStatus(supportM, radiusM) === "resolved";
}
