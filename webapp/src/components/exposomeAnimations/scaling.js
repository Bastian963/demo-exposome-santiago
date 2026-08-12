import { MAX_PARTICLES } from "./constants.js";
import { clamp01 } from "./transitions.js";
import {
  isMeasuredValue,
  parkAccessState,
  percentageCellCount,
  segmentedCount,
} from "./monitorSemantics.js";

export function getDisplayValue(baseValue, previewValue) {
  return previewValue ?? baseValue;
}

// When both bounds are configured, maps value to a normalized [0,1]
// position within the real data domain (instead of an arbitrary
// count*scale budget) so the visual output tracks how the value
// actually varies across communes. Returns null when not configured,
// so callers can fall back to the legacy behavior untouched.
function domainT(value, config = {}) {
  const vmin = config.visualMinValue;
  const vmax = config.visualMaxValue;
  if (typeof vmin !== "number" || typeof vmax !== "number" || vmax <= vmin) return null;
  return clamp01((value - vmin) / (vmax - vmin));
}

function curved(t, config = {}) {
  const gamma = config.curveGamma || 1;
  return gamma === 1 ? t : Math.pow(t, gamma);
}

// Picks usable [vmin, vmax] bounds out of a per-study domain snapshot
// (see choropleth.js computeStudyDomain): prefers p5-p95 (robust to
// outliers, e.g. AMBA's few high-pollution communes) and falls back to
// min/max when the sample is too small or the percentile span collapses.
// Returns null when the snapshot has nothing usable, so callers fall
// further back to the palette's own hand-tuned chamber domain.
function resolveStudyBounds(studyDomain) {
  if (!studyDomain) return null;
  const { min, max, p5, p95, n } = studyDomain;
  if (typeof p5 === "number" && typeof p95 === "number" && p95 > p5 && (!n || n >= 8)) {
    return { vmin: p5, vmax: p95 };
  }
  if (typeof min === "number" && typeof max === "number" && max > min) {
    return { vmin: min, vmax: max };
  }
  return null;
}

export function valueToCount(value, config = {}) {
  const maxCount = config.maxVisualCount || config.max_visual_count || MAX_PARTICLES;
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  const t = domainT(value, config);
  if (t !== null) {
    const minCount = config.minVisualCount || 0;
    return Math.round(minCount + curved(t, config) * (maxCount - minCount));
  }
  if (value <= 0) return 0;
  const scale = config.countScale || config.count_scale || 12;
  return Math.min(maxCount, Math.round(value * scale));
}

export function normalizeValue(value, config = {}) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  const t = domainT(value, config);
  if (t !== null) return curved(t, config);
  if (value <= 0) return 0;
  const explicitMax = config.visualMaxValue || config.visual_max_value;
  const maxVisualCount = config.maxVisualCount || config.max_visual_count;
  if (typeof explicitMax === "number" && explicitMax > 0) {
    return clamp01(value / explicitMax);
  }
  if (typeof maxVisualCount === "number" && maxVisualCount > 0) {
    return clamp01(valueToCount(value, config) / maxVisualCount);
  }
  return clamp01(value / 50);
}

export function valueToVisualState(value, expo = {}, studyDomain = null) {
  const chamber = expo.chamber || {};
  const rendererId = getRendererId(expo);
  const maxVisualCount =
    typeof chamber.max_visual_count === "number"
      ? chamber.max_visual_count
      : rendererId === "alan"
        ? 120
        : rendererId === "social"
          ? 100
        : rendererId === "noise"
          ? 120
        : MAX_PARTICLES;
  const countScale =
    typeof chamber.count_scale === "number"
      ? chamber.count_scale
      : rendererId === "alan"
        ? 2
        : rendererId === "social"
          ? 30
        : rendererId === "noise"
          ? 3
        : rendererId === "heat"
          ? 8
        : rendererId === "no2"
          ? 5
          : 12;
  // Hybrid domain: the active study's own value range wins (so the scene
  // discriminates in whatever city is loaded), falling back to the
  // palette's hand-tuned bounds when no study data is available yet.
  // `chamber.domain: "absolute"` opts an exposome out entirely (e.g. one
  // meant to read the same everywhere, comparable across cities).
  const studyBounds = chamber.domain === "absolute" ? null : resolveStudyBounds(studyDomain);
  const config = {
    maxVisualCount,
    countScale,
    minVisualCount: chamber.min_visual_count,
    visualMinValue: studyBounds ? studyBounds.vmin : chamber.visual_min_value,
    visualMaxValue: studyBounds ? studyBounds.vmax : chamber.visual_max_value,
    curveGamma: chamber.curve_gamma,
  };
  const defaultVisualCount = valueToCount(value, config);
  const intensity = normalizeValue(value, config);
  // The panel counter must agree with a scene whenever it names a concrete
  // visual unit. Generic particle budgets are useful to legacy renderers, but
  // would make a five-day register or a 100-cell percentage read falsely.
  const visualCount = resolvePanelVisualCount(expo, value, intensity, defaultVisualCount);
  return {
    displayValue: value,
    visualCount,
    intensity,
    density: rendererId === "pm25" ? intensity : intensity * 0.55,
    diffusion: rendererId === "no2" ? intensity : intensity * 0.35,
    radiance: rendererId === "alan" ? intensity : intensity * 0.25,
    acoustic: rendererId === "noise" ? intensity : intensity * 0.2,
    maxVisualCount,
    countScale,
  };
}

function resolvePanelVisualCount(expo, value, intensity, fallback) {
  // Palette entries are indexed by ID, but the active entry is passed through
  // several UI boundaries as the entry object itself. Its chamber variant is
  // therefore the reliable semantic identity at render time.
  const id = expo?.chamber?.variant || expo?.id;
  switch (id) {
    case "heat_hot_days":
    case "hot_day_register":
    case "rain_dry_spell":
    case "consecutive_dry_run":
      return segmentedCount(value, { blockSize: 5, maxBlocks: 24 });
    case "precipitation_spi":
    case "drought_frequency":
    case "green":
    case "land_cover":
    case "canopy":
    case "tree_canopy":
      return percentageCellCount(value, 100);
    case "greenspace_access":
    case "park_distance": {
      const access = parkAccessState(value, intensity);
      return access.status === "available" ? 2 + Math.round(access.distanceT * 8) : 0;
    }
    case "wind":
    case "turbine_field":
      return isMeasuredValue(value) ? Math.round(clamp01(intensity) * 100) : 0;
    default:
      return fallback;
  }
}

export function getRendererId(expo = {}) {
  const id = expo.id || "";
  const mode = expo.chamber?.mode;
  if (id === "food_environment" || id === "food_insecurity" || mode === "food") return "food";
  if (mode === "outcome") return "outcome";
  if (mode === "safety") return "safety";
  if (id === "walkability" || mode === "walk") return "walk";
  if (id === "green" || id === "canopy" || id === "greenspace_access" || mode === "green" || mode === "green_access") return "green";
  if (id === "wind" || mode === "wind") return "wind";
  if (id === "nse" || mode === "social" || mode === "socio_context") return "social";
  if (id === "noise" || mode === "noise" || mode === "traffic_noise") return "noise";
  if (id.startsWith("heat") || mode === "heat" || mode === "thermal") return "heat";
  if (id === "rain" || id.startsWith("rain_") || mode === "rain") return "rain";
  if (id === "alan" || mode === "streetlight" || mode === "radiance") return "alan";
  if (id === "no2") return "no2";
  return "pm25";
}
