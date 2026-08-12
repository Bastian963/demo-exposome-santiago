// PM2.5 choropleth layer + D3 legend.
// Loads the slim master.geojson, joins PM2.5 column, and renders
// a fill layer with the sequential colormap from palette.json.

import maplibregl from "maplibre-gl";
import {
  cogProtocol,
  locationValues,
  setColorFunction,
} from "@geomatico/maplibre-cog-protocol";
import { ascending, quantileSorted } from "d3-array";
import { getPalette } from "./palette.js";
import {
  studyAsset,
  assetUrl,
  studyDetailAsset,
  studyHasFineLayer,
  studySpatialIndicator,
  studyTemporalIndicator,
  temporalSeriesRequiresSpatialDetail,
  temporalSeriesSpatiallyComplete,
} from "./data-repository.js";
import { resolveExposomeDefinition } from "./utils/exposome-definition.js";
import { temporalMapLabel, withMapSupport } from "./utils/spatial-support.js";
import { joinAnnualRecords } from "./utils/temporal-data.js";
import { formatMeasuredValue } from "./utils/measurement-format.js";
import { communeNameAtPoint, mapTooltipHtml } from "./utils/map-tooltip.js";

// Stop values for the color ramp. "linear" (default) spreads the palette
// stops evenly across [vmin, vmax]; "quantile" places them at data
// quantiles so skewed layers (e.g. ALAN, log-normal radiance) keep
// contrast instead of pooling in the first color band. Opt-in per
// exposome via `"scale": "quantile"` in palette.json.
function computeStopValues(values, nStops, scaleType) {
  const sorted = [...values].sort(ascending);
  const vmin = sorted[0];
  const vmax = sorted[sorted.length - 1];
  const stopValues = [];
  for (let i = 0; i < nStops; i++) {
    const t = i / (nStops - 1);
    stopValues.push(
      scaleType === "quantile" ? quantileSorted(sorted, t) : vmin + t * (vmax - vmin),
    );
  }
  // MapLibre's interpolate expression requires strictly ascending stops;
  // nudge duplicated quantiles (heavy ties) forward by an epsilon.
  for (let i = 1; i < stopValues.length; i++) {
    if (stopValues[i] <= stopValues[i - 1]) {
      stopValues[i] = stopValues[i - 1] + (Math.abs(stopValues[i - 1]) || 1) * 1e-6;
    }
  }
  return stopValues;
}

// Robust per-study value domain for the chamber monitor: p5-p95 clamps
// outliers (e.g. AMBA's few high-pollution communes) so the scene keeps
// discriminating across the bulk of the distribution instead of getting
// crushed by a handful of extremes. scaling.js falls back to min/max, then
// to the palette's own hand-tuned chamber bounds, when this isn't usable.
function computeStudyDomain(values) {
  if (!values.length) return null;
  const sorted = [...values].sort(ascending);
  return {
    min: sorted[0],
    max: sorted[sorted.length - 1],
    p5: quantileSorted(sorted, 0.05),
    p95: quantileSorted(sorted, 0.95),
    n: sorted.length,
  };
}

// Position (0..1) of a value along the ramp defined by stopValues —
// piecewise-linear, matching how MapLibre interpolates the fill color.
function valueToT(value, stopValues) {
  const n = stopValues.length;
  if (!(n > 1)) return 0;
  if (value <= stopValues[0]) return 0;
  if (value >= stopValues[n - 1]) return 1;
  for (let i = 1; i < n; i++) {
    if (value <= stopValues[i]) {
      const span = stopValues[i] - stopValues[i - 1];
      const local = span > 0 ? (value - stopValues[i - 1]) / span : 0;
      return (i - 1 + local) / (n - 1);
    }
  }
  return 1;
}

function hexToRgba(hex) {
  const clean = String(hex || "#000000").replace("#", "");
  const value = Number.parseInt(clean.length === 3
    ? clean.split("").map((part) => `${part}${part}`).join("")
    : clean, 16);
  return [value >> 16 & 255, value >> 8 & 255, value & 255, 255];
}

function interpolateRgba(stops, t) {
  const bounded = Math.max(0, Math.min(1, t));
  const position = bounded * (stops.length - 1);
  const lower = Math.floor(position);
  const upper = Math.min(stops.length - 1, lower + 1);
  const local = position - lower;
  const a = hexToRgba(stops[lower]);
  const b = hexToRgba(stops[upper]);
  return a.map((value, index) => Math.round(value + (b[index] - value) * local));
}

function vectorContourColors(stops, count = 5) {
  if (!Array.isArray(stops) || !stops.length || count < 1) return [];
  if (count === 1) return [stops[0]];
  return Array.from({ length: count }, (_, index) => (
    stops[Math.round(index * (stops.length - 1) / (count - 1))]
  ));
}

function ensureCogProtocol() {
  if (_cogProtocolInstalled) return;
  maplibregl.addProtocol("cog", cogProtocol);
  _cogProtocolInstalled = true;
}

let _map = null;
let _masterData = null;
let _data = null;
const _layerDataCache = new Map();
let _currentExposome = null;
let _currentYear = "avg";
let _yearDataCache = {}; // year -> GeoJSON FeatureCollection
let _annualMissing = new Set(); // years whose annual GeoJSON 404'd
let _hoveredCommunePopup = null;
let _cogProtocolInstalled = false;
let _selectedCommuneSlug = null;

export async function loadMaster(map) {
  _map = map;
  const url = studyAsset("master_geojson") || "/data/master.geojson";
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load study master: ${res.status}`);
  }
  _data = await res.json();
  // Studies built on the general per-study pipeline (e.g. buenos_aires_comunas)
  // key their master.geojson on spatial_id/spatial_name; older bundles built
  // before that pipeline existed (santiago_communes) use slug/name. Normalize
  // to slug/name here, once, so every downstream reader (promoteId, click
  // handlers, tooltips, location-profile) works for both without caring.
  for (const f of _data.features || []) {
    const p = f.properties || (f.properties = {});
    if (p.slug === undefined && p.spatial_id !== undefined) p.slug = String(p.spatial_id);
    if (p.name === undefined && p.spatial_name !== undefined) p.name = p.spatial_name;
  }
  _masterData = _data;
  return _data;
}

export function getMaster() {
  return _masterData;
}

export function getActiveFeatureProperties(slug) {
  return (_data?.features || []).find((feature) => feature.properties?.slug === slug)?.properties || null;
}

async function loadLayerData(path) {
  const url = assetUrl(path);
  if (_layerDataCache.has(url)) return _layerDataCache.get(url);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load layer asset ${path}: ${response.status}`);
  let data = await response.json();
  if (Array.isArray(data.records)) data = joinAnnualRecords(_masterData, data);
  for (const feature of data.features || []) {
    const props = feature.properties || (feature.properties = {});
    if (props.slug === undefined && props.spatial_id !== undefined) props.slug = String(props.spatial_id);
    if (props.name === undefined && props.spatial_name !== undefined) props.name = props.spatial_name;
  }
  _layerDataCache.set(url, data);
  return data;
}

export async function addChoropleth(exposomeId, overrides = {}) {
  if (!_map || !_masterData) {
    throw new Error("Map or master not loaded.");
  }
  const palette = getPalette();
  const expo = palette.exposomes[exposomeId];
  if (!expo) {
    throw new Error(`Unknown exposome: ${exposomeId}`);
  }
  // `overrides` lets callers repaint the same exposome with a different
  // vintage (e.g. year tabs pass { column, yearLabel }); everything
  // downstream (range, paint, tooltip, legend) reads _currentExposome.
  // Exposomes with discrete vintages (`year_columns`) AND a `default_year`
  // default to that vintage so the first paint already shows a labeled year
  // (e.g. food_insecurity 2022, heat 2024). Without `default_year` the
  // default stays on `expo.column` — the multi-year aggregate (e.g. rain).
  const temporal = studyTemporalIndicator(exposomeId);
  const annualBlocked =
    temporalSeriesRequiresSpatialDetail(exposomeId)
    && !temporalSeriesSpatiallyComplete(exposomeId);
  const effectiveOverrides = annualBlocked
    ? { column: expo.column, yearLabel: null, data_asset: null }
    : overrides;
  const resolved = resolveExposomeDefinition(exposomeId, expo, effectiveOverrides);
  const spatialOptions = resolved.yearLabel
    ? { year: String(resolved.yearLabel) }
    : undefined;
  const spatial = studySpatialIndicator(exposomeId, spatialOptions);
  _currentExposome = withMapSupport(
    resolved,
    spatial,
  );
  const current = _currentExposome;
  current.seriesColorDomain = temporal?.color_domain || null;
  _data = current.data_asset ? await loadLayerData(current.data_asset) : _masterData;
  _clearSubcomunaHoverState();
  _hideMapValuePopup();
  try {
    _map.off("mousemove", "communes-fill", _handleCommuneMouseMove);
    _map.off("mouseleave", "communes-fill", _handleCommuneMouseLeave);
    _map.off("mousemove", "subcomuna-fill", _handleSubcomunaMouseMove);
    _map.off("mouseleave", "subcomuna-fill", _handleSubcomunaMouseLeave);
    _map.off("mousemove", _handleCogMouseMove);
    _map.off("mouseleave", _handleCogMouseLeave);
    _map.off("mousemove", "noise-contours-fill", _handleVectorContourMouseMove);
    _map.off("mouseleave", "noise-contours-fill", _handleVectorContourMouseLeave);
  } catch (_) {}

  // Compute value range for the column across all features.
  const values = _data.features
    .map((f) => f.properties[current.column])
    .filter((v) => typeof v === "number" && !isNaN(v));
  if (!values.length) {
    throw new Error(`Layer ${exposomeId} has no numeric values for ${current.column}`);
  }
  import("./visualizations/airchamber.js").then((m) => m.setStudyDomain(computeStudyDomain(values)));
  const stops = palette.data_colormaps[current.color] || palette.data_colormaps.sequential;
  const scaleValues = current.seriesColorDomain
    ? [current.seriesColorDomain.min, current.seriesColorDomain.max]
    : values;
  const stopValues = computeStopValues(scaleValues, stops.length, current.scale);

  // Remove any prior choropleth layer/source.
  if (_map.getLayer("communes-fill")) _map.removeLayer("communes-fill");
  if (_map.getLayer("communes-outline")) _map.removeLayer("communes-outline");
  if (_map.getLayer("communes-selected")) _map.removeLayer("communes-selected");
  if (_map.getLayer("subcomuna-fill")) _map.removeLayer("subcomuna-fill");
  if (_map.getLayer("cog-detail-raster")) _map.removeLayer("cog-detail-raster");
  if (_map.getLayer("noise-contours-line")) _map.removeLayer("noise-contours-line");
  if (_map.getLayer("noise-contours-fill")) _map.removeLayer("noise-contours-fill");
  if (_map.getSource("communes")) _map.removeSource("communes");
  if (_map.getSource("subcomuna")) _map.removeSource("subcomuna");
  if (_map.getSource("cog-detail")) _map.removeSource("cog-detail");
  if (_map.getSource("noise-contours")) _map.removeSource("noise-contours");
  _cogDetailAsset = null;
  _cogDetailUrl = null;
  _cogHoverSerial += 1;
  _vectorContourDetailAsset = null;

  _map.addSource("communes", {
    type: "geojson",
    data: _data,
    promoteId: "slug",
  });

  // Build a ["interpolate", ["linear"], ["get", col], ...] color ramp
  // from the palette stops at the computed stop values (linear spread or
  // data quantiles, per the exposome's `scale`).
  const interpExpr = [
    "interpolate",
    ["linear"],
    ["coalesce", ["get", current.column], stopValues[0]],
  ];
  for (let i = 0; i < stops.length; i++) {
    interpExpr.push(stopValues[i]);
    interpExpr.push(stops[i]);
  }

  _map.addLayer({
    id: "communes-fill",
    type: "fill",
    source: "communes",
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", current.column], null],
        "#27395d",
        interpExpr,
      ],
      "fill-opacity": 0.78,
    },
  });

  _map.addLayer({
    id: "communes-outline",
    type: "line",
    source: "communes",
    paint: {
      "line-color": "#1a1c2c",
      "line-width": 1.5,
      "line-opacity": 0.9,
    },
  });

  _map.addLayer({
    id: "communes-selected",
    type: "line",
    source: "communes",
    paint: {
      "line-color": "#f4b41b",
      "line-width": 3,
      "line-opacity": [
        "case",
        ["boolean", ["feature-state", "selected"], false],
        1,
        0,
      ],
    },
  });

  // A v3 study manifest is authoritative.  The palette's global flag remains
  // only for legacy bundles that have no spatial contract.
  if (studyHasFineLayer(exposomeId, spatialOptions)) {
    await addSubcomunaLayer(exposomeId, spatialOptions);
  }
  else {
    current.detailActive = false;
    current.detailColorDomain = null;
    setLegendHighlight();
    import("./visualizations/airchamber.js").then((m) => m.clearPreviewValue());
  }

  _map.on("mousemove", "communes-fill", _handleCommuneMouseMove);
  _map.on("mouseleave", "communes-fill", _handleCommuneMouseLeave);

  updateLegend();
  const airchamber = await import("./visualizations/airchamber.js");
  airchamber.setChamberCopy(current);
  return current;
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _tooltipSupportLabel(kind = "administrative") {
  const support = _currentExposome?.resolution || "unidad administrativa";
  if (kind === "administrative") return `Resumen por ${support}`;
  if (kind === "grid") return `Celda · ${support}`;
  return support;
}

function _showMapValuePopup(e, payload) {
  if (!_map || !payload.communeName) return;
  if (!_map._valuePopup) {
    _map._valuePopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 6,
      className: "pixel-popup map-value-popup",
    });
  }
  _map._valuePopup
    .setLngLat(e.lngLat)
    .setHTML(mapTooltipHtml(payload))
    .addTo(_map);
}

function _hideMapValuePopup() {
  if (_map?._valuePopup) _map._valuePopup.remove();
}

function _renderVectorContourLegend(legendEl, expo, highlightedBand = null) {
  const detail = expo.spatial?.detail;
  const bands = Array.isArray(detail?.bands) ? detail.bands : [];
  const palette = getPalette();
  const stops = palette.data_colormaps[expo.color] || palette.data_colormaps.sequential;
  const colors = vectorContourColors(stops, bands.length);
  const segments = bands.map((band, index) => `
    <div class="legend-category${highlightedBand === band.value ? " is-active" : ""}">
      <span class="legend-category-swatch" style="background:${colors[index]};"></span>
      <span class="legend-category-label">${escHtml(band.label)}</span>
    </div>
  `).join("");
  const period = temporalMapLabel(expo, _currentYear);
  legendEl.innerHTML = `
    <div class="legend-title" aria-label="${escHtml(`${expo.label}, ${period}`)}">
      <div class="legend-metric-row">
        <span class="legend-label" title="${escHtml(expo.label)}">${escHtml(expo.label)}</span>
        <span class="legend-unit">(dB(A))</span>
      </div>
      <div class="legend-period" title="${escHtml(period)}">${escHtml(period)}</div>
    </div>
    <div class="legend-categories" role="list" aria-label="Bandas Lden modeladas">
      ${segments}
    </div>
  `;
}

function updateLegend(highlightValue) {
  const legendEl = document.getElementById("legend");
  if (!legendEl || !_data || !_currentExposome) return;
  const palette = getPalette();
  const expo = _currentExposome;
  if (expo.detailActive && expo.spatial?.detail?.type === "vector_contours") {
    _renderVectorContourLegend(legendEl, expo, highlightValue);
    return;
  }
  const fixedDomain = expo.detailActive
    ? expo.detailColorDomain
    : expo.seriesColorDomain;
  const values = fixedDomain
    ? [fixedDomain.min, fixedDomain.max]
    : _data.features
      .map((f) => f.properties[expo.column])
      .filter((v) => typeof v === "number" && !isNaN(v));
  const stops = palette.data_colormaps[expo.color] || palette.data_colormaps.sequential;
  const stopValues = computeStopValues(values, stops.length, expo.scale);
  const vmin = stopValues[0];
  const vmax = stopValues[stopValues.length - 1];
  // Tick at the ramp's visual midpoint: the linear mid-value, or the
  // median when the exposome uses a quantile scale.
  const midPos = (stopValues.length - 1) / 2;
  const midLo = Math.floor(midPos);
  const midHi = Math.ceil(midPos);
  const vmid = stopValues[midLo] + (stopValues[midHi] - stopValues[midLo]) * (midPos - midLo);
  const formatLegendTick = (value) => (
    Math.abs(value) < 0.01 ? formatMeasuredValue(value) : value.toFixed(1)
  );

  const gradient = `linear-gradient(to right, ${stops.join(", ")})`;

  // If a highlight value is provided, place a marker on the gradient at
  // the same ramp position the map paints it (piecewise over the stops).
  let markerHtml = "";
  let markerLeft = 0;
  if (
    typeof highlightValue === "number" &&
    !isNaN(highlightValue) &&
    vmax > vmin
  ) {
    const t = valueToT(highlightValue, stopValues);
    markerLeft = t * 100;
    const markerUnit = expo.detailActive && expo.spatial?.detail?.unit || expo.unit;
    markerHtml = `<div class="legend-marker" style="left:${markerLeft}%" title="${formatMeasuredValue(highlightValue)} ${markerUnit}"></div>`;
  }

  // Append year suffix to title. Vintage exposomes (year_columns) pass a
  // yearLabel override composed with `period` as a short source prefix
  // ("CASEN SAE 2022", "CHIRPS 2019"); their aggregate view uses
  // `period_avg` ("CHIRPS 2015-2024"). Annual exposomes (pm25) use the
  // time-slider year.
  const yearSuffix = temporalMapLabel(expo, _currentYear);
  const legendUnit = expo.detailActive && expo.spatial?.detail?.unit || expo.unit;
  const legendAria = `${expo.label}, ${legendUnit}, ${yearSuffix}`;

  legendEl.innerHTML = `
    <div class="legend-title" aria-label="${escHtml(legendAria)}">
      <div class="legend-metric-row">
        <span class="legend-label" title="${escHtml(expo.label)}">${escHtml(expo.label)}</span>
        <span class="legend-unit">(${escHtml(legendUnit)})</span>
      </div>
      <div class="legend-period" title="${escHtml(yearSuffix)}">${escHtml(yearSuffix)}</div>
    </div>
    <div class="legend-bar-wrap">
      <div class="legend-bar" style="background:${gradient};"></div>
      ${markerHtml}
    </div>
    <div class="legend-ticks">
      <span>${formatLegendTick(vmin)}</span>
      <span>${formatLegendTick(vmid)}</span>
      <span>${formatLegendTick(vmax)}</span>
    </div>
  `;
}

export function setLegendHighlight(value, { unit } = {}) {
  updateLegend(value);
  // Also update the standalone pixel indicator (right of colorbar).
  const ind = document.getElementById("pixelIndicatorValue");
  const wrapper = document.getElementById("pixelIndicator");
  if (ind && wrapper) {
    if (typeof value === "number" && !isNaN(value)) {
      ind.textContent = formatMeasuredValue(value);
      const unitEl = document.getElementById("pixelIndicatorUnit");
      if (unitEl) unitEl.textContent = unit || _currentExposome?.unit || "";
      wrapper.hidden = false;
    } else {
      ind.textContent = "—";
      wrapper.hidden = true;
    }
  }
}

function _setLegendCategoryHighlight(bandValue) {
  updateLegend(bandValue);
  const detail = _vectorContourDetailAsset;
  const band = detail?.bands?.find((candidate) => candidate.value === bandValue);
  const ind = document.getElementById("pixelIndicatorValue");
  const wrapper = document.getElementById("pixelIndicator");
  const unitEl = document.getElementById("pixelIndicatorUnit");
  if (ind && wrapper) {
    if (band) {
      ind.textContent = band.label;
      if (unitEl) unitEl.textContent = "";
      wrapper.hidden = false;
    } else {
      ind.textContent = "—";
      wrapper.hidden = true;
    }
  }
}

// Fine-detail layer. v2 studies publish a descriptor for the asset that is
// actually available in that city (COG preferred; old GeoJSON remains a
// temporary bridge). Do NOT infer detail from a source-resolution label.
let _subcomunaData = null;
let _subcomunaExposome = null;
let _subcomunaAssetPath = null;
let _subcomunaDetailAsset = null;
let _hoveredSubcomunaPixelId = null;
let _cogDetailAsset = null;
let _cogDetailUrl = null;
let _cogHoverSerial = 0;
let _vectorContourDetailAsset = null;

function _setAdministrativeVectorOpacity(active, minzoom = 11) {
  if (!_map?.getLayer("communes-fill")) return;
  _map.setPaintProperty(
    "communes-fill",
    "fill-opacity",
    active
      ? ["interpolate", ["linear"], ["zoom"], minzoom - 0.01, 0.78, minzoom, 0.22]
      : 0.78,
  );
}

function _removeSpatialDetail() {
  if (!_map) return;
  _map.off("mousemove", _handleCogMouseMove);
  _map.off("mouseleave", _handleCogMouseLeave);
  try {
    _map.off("mousemove", "noise-contours-fill", _handleVectorContourMouseMove);
    _map.off("mouseleave", "noise-contours-fill", _handleVectorContourMouseLeave);
  } catch (_) {}
  if (_map.getLayer("noise-contours-line")) _map.removeLayer("noise-contours-line");
  if (_map.getLayer("noise-contours-fill")) _map.removeLayer("noise-contours-fill");
  if (_map.getSource("noise-contours")) _map.removeSource("noise-contours");
  if (_map.getLayer("cog-detail-raster")) _map.removeLayer("cog-detail-raster");
  if (_map.getSource("cog-detail")) _map.removeSource("cog-detail");
  if (_map.getLayer("subcomuna-fill")) _map.removeLayer("subcomuna-fill");
  if (_map.getSource("subcomuna")) _map.removeSource("subcomuna");
  _cogDetailAsset = null;
  _cogDetailUrl = null;
  _vectorContourDetailAsset = null;
  _subcomunaDetailAsset = null;
  if (_currentExposome) {
    _currentExposome.detailActive = false;
    _currentExposome.detailColorDomain = null;
  }
  _setAdministrativeVectorOpacity(false);
}

export async function addSubcomunaLayer(exposomeId, spatialOptions) {
  if (!_map) return;
  _removeSpatialDetail();
  const detail = studyDetailAsset(exposomeId, spatialOptions);
  if (detail?.type === "vector_contours") {
    _installVectorContours(detail);
    return;
  }
  if (detail?.type === "cog") {
    _installCogDetail(detail);
    return;
  }
  if (detail?.type !== "geojson") return;
  const detailPath = detail.path;
  if (
    _subcomunaExposome === exposomeId
    && _subcomunaAssetPath === detailPath
    && _subcomunaData
  ) {
    _subcomunaDetailAsset = detail;
    _installSubcomunaSource();
    return;
  }
  try {
    const res = await fetch(
      assetUrl(detailPath),
    );
    if (!res.ok) {
      _subcomunaData = null;
      _subcomunaExposome = null;
      _subcomunaAssetPath = null;
      _subcomunaDetailAsset = null;
      return;
    }
    _subcomunaData = await res.json();
    _subcomunaExposome = exposomeId;
    _subcomunaAssetPath = detailPath;
    _subcomunaDetailAsset = detail;
    _installSubcomunaSource();
  } catch (err) {
    console.warn(`addSubcomunaLayer(${exposomeId}) failed:`, err);
  }
}

function _installCogDetail(detail) {
  if (!_map || !_currentExposome) return;
  const url = assetUrl(detail.path);
  if (!url) return;
  ensureCogProtocol();
  _cogDetailAsset = detail;
  _cogDetailUrl = url;
  const values = _data.features
    .map((feature) => feature.properties[_currentExposome.column])
    .filter((value) => typeof value === "number" && !Number.isNaN(value));
  const range = detail.color_domain || {
    min: Math.min(...values),
    max: Math.max(...values),
  };
  _currentExposome.detailActive = true;
  _currentExposome.detailColorDomain = range;
  const palette = getPalette();
  const stops = palette.data_colormaps[_currentExposome.color] || palette.data_colormaps.sequential;
  // The COG protocol invokes this function with raw source values, preserving
  // the scientific quantity rather than pre-colouring a second raster.
  setColorFunction(url, (pixel, color, metadata) => {
    const value = Number(pixel[detail.band ? detail.band - 1 : 0]);
    if (!Number.isFinite(value) || value === metadata.noData || !(range.max > range.min)) {
      color.set([0, 0, 0, 0]);
      return;
    }
    color.set(interpolateRgba(stops, (value - range.min) / (range.max - range.min)));
  });
  _map.addSource("cog-detail", {
    type: "raster",
    url: `cog://${url}`,
    tileSize: 256,
  });
  _map.addLayer({
    id: "cog-detail-raster",
    type: "raster",
    source: "cog-detail",
    paint: { "raster-opacity": 0.9, "raster-resampling": "nearest" },
  });
  if (_map.getLayer("communes-outline")) _map.moveLayer("cog-detail-raster", "communes-outline");
  _map.on("mousemove", _handleCogMouseMove);
  _map.on("mouseleave", _handleCogMouseLeave);
  updateLegend();
}

function _installVectorContours(detail) {
  if (!_map || !_currentExposome) return;
  const tileUrls = detail.tiles.map((path) => assetUrl(path));
  if (tileUrls.some((url) => !url)) return;
  _vectorContourDetailAsset = detail;
  _currentExposome.detailActive = true;
  _currentExposome.detailColorDomain = null;
  const palette = getPalette();
  const stops = palette.data_colormaps[_currentExposome.color] || palette.data_colormaps.sequential;
  const colors = vectorContourColors(stops, detail.bands.length);
  const match = ["match", ["get", "lden_band"]];
  detail.bands.forEach((band, index) => {
    match.push(band.value, colors[index]);
  });
  match.push("rgba(0,0,0,0)");
  _map.addSource("noise-contours", {
    type: "vector",
    tiles: tileUrls,
    minzoom: detail.minzoom,
    maxzoom: detail.maxzoom,
    bounds: detail.bounds,
  });
  _map.addLayer({
    id: "noise-contours-fill",
    type: "fill",
    source: "noise-contours",
    "source-layer": detail.source_layer,
    minzoom: detail.minzoom,
    layout: { "fill-sort-key": ["get", "band_priority"] },
    paint: {
      "fill-color": match,
      "fill-opacity": [
        "case",
        ["boolean", ["feature-state", "hover"], false],
        0.98,
        0.88,
      ],
    },
  });
  _map.addLayer({
    id: "noise-contours-line",
    type: "line",
    source: "noise-contours",
    "source-layer": detail.source_layer,
    minzoom: detail.minzoom,
    paint: {
      "line-color": "rgba(26, 28, 44, 0.72)",
      "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.55, 15, 1.1],
    },
  });
  if (_map.getLayer("communes-outline")) {
    _map.moveLayer("noise-contours-fill", "communes-outline");
    _map.moveLayer("noise-contours-line", "communes-outline");
  }
  _setAdministrativeVectorOpacity(true, detail.minzoom);
  _map.on("mousemove", "noise-contours-fill", _handleVectorContourMouseMove);
  _map.on("mouseleave", "noise-contours-fill", _handleVectorContourMouseLeave);
  updateLegend();
}

function _handleVectorContourMouseMove(e) {
  if (!_map || !_currentExposome || !_vectorContourDetailAsset || !e.features?.[0]) return;
  _map.getCanvas().style.cursor = "crosshair";
  const value = String(e.features[0].properties?.lden_band || "");
  const band = _vectorContourDetailAsset.bands.find((candidate) => candidate.value === value);
  if (!band) {
    _restoreSelectedContext();
    return;
  }
  const communeName = communeNameAtPoint(_map, e.point, "—");
  _setLegendCategoryHighlight(value);
  import("./visualizations/airchamber.js").then((module) => module.clearPreviewValue());
  _showMapValuePopup(e, {
    communeName,
    metricLabel: "Banda Lden modelada",
    valueText: band.label,
    unit: "",
    supportLabel: _tooltipSupportLabel("vector"),
  });
}

function _handleVectorContourMouseLeave() {
  if (_map) _map.getCanvas().style.cursor = "";
  _restoreSelectedContext();
}

async function _handleCogMouseMove(e) {
  if (!_map || !_currentExposome || !_cogDetailUrl || !_cogDetailAsset) return;
  _map.getCanvas().style.cursor = "crosshair";
  const serial = ++_cogHoverSerial;
  const communeName = communeNameAtPoint(_map, e.point);
  if (!communeName) {
    _restoreSelectedContext();
    return;
  }
  try {
    const values = await locationValues(_cogDetailUrl, {
      latitude: e.lngLat.lat,
      longitude: e.lngLat.lng,
    }, _map.getZoom());
    if (serial !== _cogHoverSerial) return;
    if (!Array.isArray(values)) {
      _restoreSelectedContext();
      return;
    }
    const value = Number(values[(_cogDetailAsset.band || 1) - 1]);
    if (!Number.isFinite(value)) {
      _restoreSelectedContext();
      return;
    }
    const unit = _cogDetailAsset.unit || _currentExposome.unit;
    const metricLabel = _cogDetailAsset.metric_label || _currentExposome.label;
    const range = _currentExposome.detailColorDomain;
    setLegendHighlight(value, { unit });
    // COG lookups resolve asynchronously. Keep the serial guard so a late
    // response cannot replace the monitor preview for a newer cursor position.
    import("./visualizations/airchamber.js").then((m) => {
      if (serial === _cogHoverSerial) m.previewValue(value, {
        domain: {
          min: range.min,
          max: range.max,
          p5: range.min,
          p95: range.max,
          n: 1,
        },
        unit,
        metricLabel,
      });
    });
    _showMapValuePopup(e, {
      communeName,
      metricLabel,
      value,
      unit,
      supportLabel: _tooltipSupportLabel("cog"),
    });
  } catch (error) {
    // Query failures are expected outside the AOI mask or while a source is
    // being replaced. The raster itself remains usable.
    if (serial === _cogHoverSerial) {
      console.debug("COG value query failed", error);
      _restoreSelectedContext();
    }
  }
}

function _handleCogMouseLeave() {
  _cogHoverSerial += 1;
  if (_map) _map.getCanvas().style.cursor = "";
  _restoreSelectedContext();
}

function _selectedCommuneValue() {
  if (!_selectedCommuneSlug || !_currentExposome) return null;
  const activeData = _currentYear !== "avg" ? _yearDataCache[_currentYear] : null;
  const feature = (activeData?.features || _data?.features || []).find(
    (item) => item.properties?.slug === _selectedCommuneSlug,
  );
  const value = feature?.properties?.[_currentExposome.column];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function _restoreSelectedContext() {
  _hideMapValuePopup();
  if (_vectorContourDetailAsset) {
    _setLegendCategoryHighlight(null);
    import("./visualizations/airchamber.js").then((m) => m.clearPreviewValue());
    return;
  }
  const selected = _selectedCommuneValue();
  const detailUnit = _cogDetailAsset?.unit;
  if (selected != null && (!detailUnit || detailUnit === _currentExposome?.unit)) {
    setLegendHighlight(selected, { unit: _currentExposome?.unit });
  } else {
    // A commune-level proxy in another unit cannot be marked on the raster
    // legend (NO2 surface µg/m³ versus tropospheric column mol/m²).
    setLegendHighlight();
  }
  import("./visualizations/airchamber.js").then((m) => m.clearPreviewValue());
}

function _installSubcomunaSource() {
  if (!_map || !_data || !_subcomunaData || !_currentExposome) return;
  _clearSubcomunaHoverState();
  try {
    _map.off("mousemove", "subcomuna-fill", _handleSubcomunaMouseMove);
    _map.off("mouseleave", "subcomuna-fill", _handleSubcomunaMouseLeave);
  } catch (e) {
    // ignore listener teardown when the layer is not yet attached
  }
  if (_map.getLayer("subcomuna-fill")) _map.removeLayer("subcomuna-fill");
  if (_map.getSource("subcomuna")) _map.removeSource("subcomuna");
  _map.addSource("subcomuna", {
    type: "geojson",
    data: _subcomunaData,
    promoteId: "pixel_id",
  });
  const palette = getPalette();
  const expo = _currentExposome;
  const detailDomain = _subcomunaDetailAsset?.color_domain;
  const values = detailDomain
    ? [detailDomain.min, detailDomain.max]
    : expo.seriesColorDomain
      ? [expo.seriesColorDomain.min, expo.seriesColorDomain.max]
    : _data.features
      .map((f) => f.properties[expo.column])
      .filter((v) => typeof v === "number");
  if (!values.length) return;
  // Same domain and scale as the commune fill so pixel and commune colors
  // stay comparable.
  const stops = palette.data_colormaps[expo.color] || palette.data_colormaps.sequential;
  const stopValues = computeStopValues(values, stops.length, expo.scale);
  const interpExpr = [
    "interpolate",
    ["linear"],
    ["coalesce", ["get", "value"], stopValues[0]],
  ];
  for (let i = 0; i < stops.length; i++) {
    interpExpr.push(stopValues[i]);
    interpExpr.push(stops[i]);
  }
  _map.addLayer({
    id: "subcomuna-fill",
    type: "fill",
    source: "subcomuna",
    paint: {
      "fill-color": interpExpr,
      "fill-opacity": [
        "case",
        ["boolean", ["feature-state", "hover"], false],
        1,
        0.9,
      ],
      "fill-outline-color": [
        "case",
        ["boolean", ["feature-state", "hover"], false],
        "#f4f4f4",
        "rgba(13, 14, 26, 0.4)",
      ],
    },
  });
  // Place sub-comuna between the commune fill (below) and the
  // commune outline (above) so the squares are visible over the
  // choropleth but the boundary lines remain on top as delimiters.
  // Note: moveLayer(id, beforeId) puts id BEFORE beforeId, which
  // means id is rendered BELOW beforeId in z-order.
  if (_map.getLayer("communes-outline")) {
    _map.moveLayer("subcomuna-fill", "communes-outline");
  }

  // Hover on sub-comuna squares: show the pixel value in a popup.
  // While this layer is present the commune-level popup is suppressed
  // (see the communes-fill mousemove handler), so only this pixel
  // popup shows — no overlapping duplicate.
  _map.on("mousemove", "subcomuna-fill", _handleSubcomunaMouseMove);
  _map.on("mouseleave", "subcomuna-fill", _handleSubcomunaMouseLeave);
}

function _handleCommuneMouseMove(e) {
  if (!_map || !_currentExposome) return;
  _map.getCanvas().style.cursor = "pointer";
  if (_map.getLayer("subcomuna-fill") || _map.getLayer("cog-detail-raster")) return;
  if (
    _map.getLayer("noise-contours-fill")
    && _map.queryRenderedFeatures(e.point, { layers: ["noise-contours-fill"] }).length
  ) return;
  if (!e.features || !e.features[0]) return;
  const f = e.features[0];
  const name = f.properties.name;
  const val = f.properties[_currentExposome.column];
  if (typeof val === "number" && !isNaN(val)) {
    setLegendHighlight(val);
    import("./visualizations/airchamber.js").then((m) => m.previewValue(val));
  }
  _showMapValuePopup(e, {
    communeName: name,
    metricLabel: _currentExposome.label,
    value: val,
    unit: _currentExposome.unit,
    supportLabel: _tooltipSupportLabel("administrative"),
  });
}

function _handleCommuneMouseLeave() {
  if (!_map) return;
  _map.getCanvas().style.cursor = "";
  _hideMapValuePopup();
  _restoreSelectedContext();
}

function _handleSubcomunaMouseMove(e) {
  if (!_map || !_currentExposome || !e.features || !e.features[0]) return;
  const f = e.features[0];
  const pixelId = f.properties.pixel_id;
  const v = f.properties.value;
  const communeName = communeNameAtPoint(
    _map,
    e.point,
    f.properties.commune_name || f.properties.commune_slug || "—",
  );
  _hideMapValuePopup();

  if (pixelId && pixelId !== _hoveredSubcomunaPixelId) {
    _clearSubcomunaHoverState();
    _hoveredSubcomunaPixelId = pixelId;
    _map.setFeatureState(
      { source: "subcomuna", id: pixelId },
      { hover: true },
    );
    if (typeof v === "number" && !isNaN(v)) {
      const unit = _subcomunaDetailAsset?.unit || _currentExposome.unit;
      setLegendHighlight(v, { unit });
      import("./visualizations/airchamber.js").then((m) => m.previewValue(v));
    }
  } else if (!pixelId && typeof v === "number" && !isNaN(v)) {
    setLegendHighlight(v);
    import("./visualizations/airchamber.js").then((m) => m.previewValue(v));
  }

  _showMapValuePopup(e, {
    communeName,
    metricLabel: _subcomunaDetailAsset?.metric_label || _currentExposome.label,
    value: v,
    unit: _subcomunaDetailAsset?.unit || _currentExposome.unit,
    supportLabel: _tooltipSupportLabel("grid"),
  });
}

function _handleSubcomunaMouseLeave() {
  _clearSubcomunaHoverState();
  _restoreSelectedContext();
}

function _clearSubcomunaHoverState() {
  if (_map && _hoveredSubcomunaPixelId != null) {
    try {
      _map.setFeatureState(
        { source: "subcomuna", id: _hoveredSubcomunaPixelId },
        { hover: false },
      );
    } catch (e) {
      // ignore stale feature-state cleanup when source is being replaced
    }
  }
  _hoveredSubcomunaPixelId = null;
}

// Set the current year and update the choropleth source.
// year: "avg" for multi-year average, or a specific year (e.g. 2015-2022).
// Annual data files live at /data/annual/<exposomeId>_<year>.geojson.
export async function setYear(year) {
  _currentYear = year;
  if (year === "avg") {
    // Multi-year average: use the already-loaded _data. getSource can
    // throw on a destroyed/not-yet-loaded map (e.g. during view
    // transitions), so guard it instead of only null-checking _map.
    try {
      if (_map && _map.getSource("communes")) {
        _map.getSource("communes").setData(_data);
      }
    } catch (_) { /* map not ready or already destroyed */ }
    updateLegend();
    return;
  }
  // Specific year: lazy load the annual GeoJSON.
  if (_yearDataCache[year]) {
    try {
      if (_map && _map.getSource("communes")) {
        _map.getSource("communes").setData(_yearDataCache[year]);
      }
    } catch (_) { /* map not ready or already destroyed */ }
    updateLegend();
    return;
  }
  // Already known to be missing: don't re-fetch. This avoids a 404 storm
  // when the user hits "Play" and cycles through years that have no
  // annual file yet (see docs/time_series_data.md).
  if (_annualMissing.has(year)) {
    window.__app?.notifyAnnualDataMissing?.(year);
    return;
  }
  try {
    const res = await fetch(
      assetUrl(`annual/${_currentExposome.id}_${year}.geojson`) ||
        `/data/annual/${_currentExposome.id}_${year}.geojson`,
    );
    if (!res.ok) {
      // Annual data not generated yet - remember it and notify once.
      _annualMissing.add(year);
      console.warn(`Annual data for ${year} not available (HTTP ${res.status}). See docs/time_series_data.md.`);
      window.__app?.notifyAnnualDataMissing?.(year);
      return;
    }
    _yearDataCache[year] = await res.json();
    try {
      if (_map && _map.getSource("communes")) {
        _map.getSource("communes").setData(_yearDataCache[year]);
      }
    } catch (_) { /* map not ready or already destroyed */ }
    updateLegend();
  } catch (e) {
    _annualMissing.add(year);
    console.warn(`Failed to load annual data for ${year}:`, e);
    window.__app?.notifyAnnualDataMissing?.(year);
  }
}

export function selectCommune(slug) {
  if (!_map) return;
  _selectedCommuneSlug = slug || null;
  // Clear all selected states.
  const activeData = _currentYear !== "avg" ? _yearDataCache[_currentYear] : null;
  const activeFeatures = activeData?.features || _data.features;
  for (const f of activeFeatures) {
    _map.setFeatureState(
      { source: "communes", id: f.properties.slug },
      { selected: false },
    );
  }
  // Set the new one.
  if (slug) {
    _map.setFeatureState(
      { source: "communes", id: slug },
      { selected: true },
    );
  }
  // Update legend with this commune's value.
  if (slug && _currentExposome) {
    const feat = activeFeatures.find(
      (f) => f.properties.slug === slug,
    );
    if (feat) {
      const v = feat.properties[_currentExposome.column];
      if (typeof v === "number" && !isNaN(v)) {
        updateLegend(v);
      } else {
        updateLegend();
      }
    }
  } else {
    // No commune selected: clear the marker.
    updateLegend();
  }
}
