// Study-aware data access for the webapp.
// All city-specific URLs are resolved here so the rest of the UI never knows
// whether data is served locally or from a versioned object-store prefix.

import { spatialUnitLabel } from "./utils/spatial-unit.js";

const DEFAULT_BASE = "/data";
const DATA_BASE = String(
  globalThis.__EXPOSOME_DATA_BASE__ ||
    (typeof import.meta !== "undefined" && import.meta.env?.VITE_DATA_BASE_URL) ||
    DEFAULT_BASE,
).replace(/\/$/, "");

let _catalog = null;
let _study = null;
let _record = null;
let _generation = 0;
let _outcomesCatalog = null;
let _associations = null;

export function dataUrl(path) {
  const clean = String(path || "").replace(/^\//, "");
  return `${DATA_BASE}/${clean}`;
}

export function getDataBase() {
  return DATA_BASE;
}

export async function loadCatalog() {
  if (_catalog) return _catalog;
  const modern = await fetch(dataUrl("catalog.json"));
  if (modern.ok) {
    _catalog = await modern.json();
    return _catalog;
  }
  // Compatibility with the pre-manifest Santiago demo. This fallback can be
  // removed once the first generated catalog is committed to a deployment.
  const legacy = await fetch(dataUrl("cities.json"));
  if (!legacy.ok) throw new Error(`Failed to load data catalog: ${modern.status}`);
  const old = await legacy.json();
  const cities = old.cities || [];
  _catalog = {
    schema_version: 0,
    default_study: "santiago_communes",
    cities,
    continents: old.continents || {},
    studies: cities.map((city) => ({
      study_id: city.study_id || `${city.slug}_communes`,
      city: city.slug,
      name: city.name,
      country: city.country,
      country_code: city.country_code || "CL",
      mode: "aggregate",
      available: city.available,
      bundle: null,
      layers: [],
    })),
  };
  return _catalog;
}

export function getCatalog() {
  return _catalog;
}

export function getStudyRecord(studyId) {
  return (_catalog?.studies || []).find((item) => item.study_id === studyId) || null;
}

export function getCityRecord(citySlug) {
  return (_catalog?.cities || []).find((item) => item.slug === citySlug) || null;
}

export async function selectStudy(studyId) {
  const catalog = await loadCatalog();
  const record = getStudyRecord(studyId) || catalog.studies?.find((item) => item.available);
  if (!record || !record.available) {
    throw new Error(`Study ${studyId || "<unset>"} has no published bundle`);
  }
  const generation = ++_generation;
  let manifest;
  if (record.bundle) {
    const response = await fetch(dataUrl(`${record.bundle}/manifest.json`));
    if (!response.ok) throw new Error(`Failed to load study manifest: ${response.status}`);
    manifest = await response.json();
  } else {
    // Legacy root assets are treated as a temporary aggregate bundle.
    manifest = {
      schema_version: 0,
      study_id: record.study_id,
      mode: "aggregate",
      location: { id: record.city, name: record.name, country: record.country },
      assets: {
        master_geojson: { path: "master.geojson" },
        master_csv: { path: "master.csv" },
        profiles: { path: "profiles", type: "directory" },
        methodology: { path: "methodology", type: "directory" },
        sources: { path: "sources.json" },
      },
      layers: Object.fromEntries((record.layers || []).map((id) => [id, { available: true }])),
    };
  }
  if (generation !== _generation) return _study;
  _record = record;
  _study = manifest;
  _study.__bundle = record.bundle || "";
  _outcomesCatalog = null;
  _associations = null;
  return _study;
}

export function getStudyManifest() {
  return _study;
}

export function getSelectedStudyId() {
  return _study?.study_id || _record?.study_id || null;
}

export function assetUrl(assetOrPath) {
  if (!assetOrPath) return null;
  const path = typeof assetOrPath === "string" ? assetOrPath : assetOrPath.path;
  if (!path) return null;
  const bundle = _study?.__bundle;
  return dataUrl(bundle ? `${bundle}/${path}` : path);
}

export function studyAsset(name) {
  return assetUrl(_study?.assets?.[name]);
}

export function layerIsAvailable(layerId) {
  return Boolean(_study?.layers?.[layerId]);
}

// v2 bundles declare the spatial support of each public exposome in the
// manifest.  This is deliberately independent from palette.json: palette
// describes presentation, while this record says what this *study* actually
// rendered and whether administrative polygons were merely a mask.
export function detailSupportsYear(detail, year) {
  const support = detail?.temporal_support;
  if (!support) return true;
  if (support.kind === "year") {
    if (year === undefined || year === null || year === "" || year === "avg") return false;
    return String(support.year) === String(year);
  }
  if (support.kind === "period") {
    return year === undefined || year === null || year === "" || year === "avg";
  }
  return false;
}

function administrativeSpatialFallback(record) {
  const label = spatialUnitLabel(_study?.spatial?.unit_type);
  return {
    ...record,
    detail: null,
    boundary_role: "analysis_unit",
    rendered: {
      kind: "administrative_polygon",
      label,
      resolution: null,
    },
  };
}

function annualDetailIsValid(detail, year) {
  if (!detail || detail.source_support_preserved !== true || !detailSupportsYear(detail, year)) {
    return false;
  }
  if (detail.type === "cog") {
    return detail.canonical_resolution_verified === true;
  }
  if (detail.type === "geojson") {
    return detail.analysis_grid_verified === true
      && detail.grid_alignment === "study_aoi_metric_grid";
  }
  return false;
}

const NOISE_VECTOR_BANDS = ["55-59", "60-64", "65-69", "70-74", "gt75"];

function validSha256(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/i.test(value);
}

export function vectorContourDetailIsValid(detail) {
  if (!detail || detail.type !== "vector_contours") return false;
  if (detail.source_support_preserved !== true) return false;
  if (detail.minzoom !== 11 || detail.maxzoom !== 15) return false;
  if (detail.source_layer !== "noise_lden") return false;
  if (!Array.isArray(detail.tiles)
    || detail.tiles.length !== 1
    || detail.tiles[0] !== "detail/noise_lden/{z}/{x}/{y}.pbf") return false;
  if (!Array.isArray(detail.bounds) || detail.bounds.length !== 4
    || !detail.bounds.every((value) => Number.isFinite(Number(value)))) return false;
  if (!Array.isArray(detail.bands)
    || detail.bands.map((band) => band?.value).join(",") !== NOISE_VECTOR_BANDS.join(",")) return false;
  if (!validSha256(detail.source_manifest_sha256)) return false;
  if (!Array.isArray(detail.source_assets) || !detail.source_assets.length
    || detail.source_assets.some((asset) => !asset?.path || !validSha256(asset.sha256))) return false;
  if (detail.source_assets.length === 1
    && detail.source_sha256 !== detail.source_assets[0].sha256) return false;
  if (detail.source_assets.length > 1 && detail.source_sha256 != null) return false;
  return detail.validation?.path === "detail/noise_lden.vector_contours.validation.json"
    && validSha256(detail.validation?.sha256);
}

export function temporalSeriesRequiresSpatialDetail(exposomeId) {
  const temporal = studyTemporalIndicator(exposomeId);
  if (temporal?.spatial_target && typeof temporal.spatial_target === "object") {
    return temporal.spatial_target.required_for_production === true;
  }
  // Compatibility for already-published schema-v3 bundles. Before the
  // temporal target field existed, the per-indicator publication target was
  // still authoritative and lets the upgraded UI fail closed immediately.
  return _study?.spatial_indicators?.[exposomeId]
    ?.publication_target?.required_for_production === true;
}

export function temporalSeriesSpatiallyComplete(exposomeId) {
  const temporal = studyTemporalIndicator(exposomeId);
  if (!temporalSeriesRequiresSpatialDetail(exposomeId)) return true;
  const expected = Array.isArray(temporal?.expected_years)
    ? temporal.expected_years.map(String)
    : Object.keys(temporal?.years || {}).filter((year) => /^\d{4}$/.test(year));
  if (!expected.length || !temporal?.years || typeof temporal.years !== "object") {
    return false;
  }
  return expected.every((year) => {
    const record = temporal.years[year];
    return Boolean(record?.asset?.path) && annualDetailIsValid(record?.detail, year);
  });
}

function unavailableTemporalSpatial(record, temporal, year) {
  return {
    ...record,
    detail: null,
    boundary_role: "mask_only",
    temporal_unavailable: true,
    rendered: {
      kind: "unavailable",
      label: `cosecha espacial ${year} no publicada`,
      resolution: null,
    },
    spatial_target: temporal?.spatial_target || null,
  };
}

function annualSpatialRecord(record, temporal, detail) {
  const resolution = detail.type === "cog"
    ? { value: detail.source_native_resolution_m, unit: "m" }
    : { value: detail.analysis_resolution_m, unit: "m" };
  return {
    ...record,
    boundary_role: "mask_only",
    rendered: {
      kind: detail.type,
      label: detail.metric_label || record?.rendered?.label || "detalle espacial anual",
      resolution,
    },
    detail: {
      ...detail,
      color_domain: temporal?.color_domain || detail.color_domain,
    },
  };
}

export function studySpatialIndicator(exposomeId, { year } = {}) {
  const record = _study?.spatial_indicators?.[exposomeId] || null;
  if (!record) return null;
  const temporal = studyTemporalIndicator(exposomeId);
  const annual = year !== undefined && year !== null && year !== "" && year !== "avg"
    ? temporal?.years?.[String(year)]
    : null;
  const annualDetail = annual?.detail;
  if (annualDetail) {
    if (!annualDetailIsValid(annualDetail, year)) {
      return temporalSeriesRequiresSpatialDetail(exposomeId)
        ? unavailableTemporalSpatial(record, temporal, year)
        : administrativeSpatialFallback(record);
    }
    return annualSpatialRecord(record, temporal, annualDetail);
  }
  // Schema v3 COGs must prove that their native source scale matches the
  // canonical scientific support. Older/stale bundle descriptors are hidden
  // rather than rendered with false precision.
  if (
    _study?.schema_version >= 3
    && record.detail?.type === "cog"
    && record.detail.canonical_resolution_verified !== true
  ) {
    return administrativeSpatialFallback(record);
  }
  if (
    _study?.schema_version >= 3
    && record.detail?.type === "vector_contours"
    && !vectorContourDetailIsValid(record.detail)
  ) {
    return administrativeSpatialFallback(record);
  }
  if (record.detail?.temporal_support && !detailSupportsYear(record.detail, year)) {
    return administrativeSpatialFallback(record);
  }
  // A declared annual harvest must never inherit a period/undated COG.  If no
  // matching annual detail exists, the truthful fallback is its administrative
  // table. A base COG explicitly scoped to this exact year (heat 2024) remains
  // valid through the temporal_support branch above.
  if (annual && !record.detail?.temporal_support) {
    return temporalSeriesRequiresSpatialDetail(exposomeId)
      ? unavailableTemporalSpatial(record, temporal, year)
      : administrativeSpatialFallback(record);
  }
  if (annual && record.detail?.temporal_support?.kind !== "year") {
    return temporalSeriesRequiresSpatialDetail(exposomeId)
      ? unavailableTemporalSpatial(record, temporal, year)
      : administrativeSpatialFallback(record);
  }
  if (
    record.detail
    && temporal?.color_domain
    && (year === undefined || year === null || year === "" || year === "avg")
  ) {
    return {
      ...record,
      detail: { ...record.detail, color_domain: temporal.color_domain },
    };
  }
  return record;
}

export function studyDetailAsset(exposomeId, options) {
  return studySpatialIndicator(exposomeId, options)?.detail || null;
}

// Per-study asset gating: lets the UI ask what the ACTIVE study's bundle
// actually ships instead of trusting the exposome's globally-declared
// has_fine_layer/has_annual flags, which describe the source's native
// resolution and are true for every city regardless of whether that
// city's bundle was published with the matching asset (e.g. AMBA has no
// subcomuna/ directory yet, so its pm25 fine layer would otherwise 404).
export function studyHasFineLayer(exposomeId, options) {
  // A v2 manifest is authoritative even when it deliberately publishes no
  // detail for a source that has fine native data.  Falling through to a
  // global palette flag here would recreate the false-precision bug.
  if (_study?.schema_version >= 2) return Boolean(studyDetailAsset(exposomeId, options));
  const asset = _study?.assets?.subcomuna;
  if (!asset) return false;
  // Directory assets only started listing their files with the exact
  // per-exposome geojsons once publishing.py grew that feature; older
  // bundles carry just the bare directory marker, so fall back to "the
  // bundle has a subcomuna dir at all" until they're republished.
  if (Array.isArray(asset.files)) return asset.files.includes(`${exposomeId}.geojson`);
  return true;
}

export function studyAnnualYears(exposomeId) {
  const temporal = studyTemporalIndicator(exposomeId);
  if (temporalSeriesRequiresSpatialDetail(exposomeId) && !temporalSeriesSpatiallyComplete(exposomeId)) {
    return [];
  }
  const declared = temporal?.years;
  if (declared && typeof declared === "object") {
    return Object.keys(declared).filter((year) => /^\d{4}$/.test(year)).sort();
  }
  const files = _study?.assets?.annual?.files;
  if (!Array.isArray(files)) return [];
  const prefix = `${exposomeId}_`;
  return files
    .filter((f) => f.startsWith(prefix) && f.endsWith(".geojson"))
    .map((f) => f.slice(prefix.length, -".geojson".length))
    .filter((year) => /^\d{4}$/.test(year));
}

export function studyTemporalIndicator(exposomeId) {
  return _study?.temporal_indicators?.[exposomeId] || null;
}

export function studyTemporalYear(exposomeId, year) {
  return studyTemporalIndicator(exposomeId)?.years?.[String(year)] || null;
}

export function studyHasColumn(column) {
  const columns = _study?.columns;
  if (!Array.isArray(columns) || !columns.length) return true;
  return columns.includes(column);
}

export async function loadOutcomesCatalog() {
  if (_outcomesCatalog) return _outcomesCatalog;
  const url = studyAsset("outcomes_catalog");
  if (!url) return null;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load outcomes catalog: ${response.status}`);
  _outcomesCatalog = await response.json();
  return _outcomesCatalog;
}

export async function loadAssociations() {
  if (_associations) return _associations;
  const url = studyAsset("associations");
  if (!url) return null;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load associations: ${response.status}`);
  _associations = await response.json();
  return _associations;
}

// Cross-city distribution comparison artifact (precomputed by
// scripts/export_webapp_distributions.py). Unlike the study-scoped loaders
// above, this does NOT depend on the active study -- it is not cleared by
// selectStudy()/resetStudyRepository() and is fetched once for the whole
// session.
let _distributions = null;

export async function loadDistributions() {
  if (_distributions) return _distributions;
  const response = await fetch(dataUrl("v1/analytics/distributions.json"));
  if (!response.ok) throw new Error(`Failed to load distributions: ${response.status}`);
  _distributions = await response.json();
  return _distributions;
}

export function resetStudyRepository() {
  _catalog = null;
  _study = null;
  _record = null;
  _outcomesCatalog = null;
  _associations = null;
  _generation += 1;
}
