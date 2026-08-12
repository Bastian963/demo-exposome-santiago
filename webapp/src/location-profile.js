import { getPalette } from "./palette.js";
import {
  featureContainsPoint,
  geometryContainsPoint,
} from "./utils/geometry.js";
import {
  getMaster,
  selectCommune,
} from "./choropleth.js";
import {
  assetUrl,
  getSelectedStudyId,
  getStudyManifest,
  studyDetailAsset,
  studyHasFineLayer,
  studySpatialIndicator,
} from "./data-repository.js";
import { mapSupportLabel } from "./utils/spatial-support.js";

const WIDGET_COLLAPSE_KEY = "gemma.locWidget.collapsed";

let _map = null;
let _widget = null;
let _card = null;
let _avatar = null;
let _status = null;
let _zipInput = null;
let _getState = () => ({});
let _updateState = () => {};
let _axesConfig = null;
let _zipcodes = null;
let _master = null;
let _pickMode = false;
let _activePoint = null;
let _dragging = false;
let _mapClickWired = false;
let _mapMoveWired = false;

const _subcomunaCache = new Map();
const _distributionCache = new Map();

export async function initLocationProfile(options = {}) {
  _map = options.map || _map;
  _getState = options.getState || _getState;
  _updateState = options.updateState || _updateState;

  _widget = document.getElementById("locationProfileWidget");
  _card = document.getElementById("locationProfileCard");
  _avatar = document.getElementById("locationProfileAvatar");
  _status = document.getElementById("locationProfileStatus");
  _zipInput = document.getElementById("locationZipInput");

  if (!_widget || !_card || !_avatar || !_map) return;

  await Promise.all([loadAxesConfig(), loadZipcodes(), ensureMaster()]);
  wireDom();
  wireMap();
  _widget.hidden = false;
  applyPersistedCollapse();
  renderEmptyCard();
}

export function destroyLocationProfile() {
  if (_map && _mapClickWired) {
    try { _map.off("click", handleMapClick); } catch (_) {}
  }
  if (_map && _mapMoveWired) {
    try { _map.off("move", updateAvatarPosition); } catch (_) {}
  }
  _mapClickWired = false;
  _mapMoveWired = false;
  _pickMode = false;
  _activePoint = null;
  _dragging = false;
  document.body.classList.remove("location-profile-pick-mode");
  if (_widget) _widget.hidden = true;
  if (_card) _card.hidden = true;
  if (_avatar) {
    _avatar.hidden = true;
    _avatar.classList.remove("is-dragging");
  }
}

export function openLocationProfilePicker() {
  if (!_widget || !_card) return;
  _widget.hidden = false;
  _card.hidden = false;
  _pickMode = true;
  document.body.classList.add("location-profile-pick-mode");
  setStatus("Haz click en el mapa o arrastra el monito.");
  if (!_activePoint) renderEmptyCard();
}

export async function restoreLocationProfileFromState(state = _getState()) {
  if (!state) return false;
  if (state.zip) {
    const ok = await setLocationFromZipcode(state.zip, { updateUrl: true, fly: true });
    if (ok) return true;
  }
  const loc = parseLocationParam(state.loc);
  if (loc) {
    await setLocationPoint(loc.lon, loc.lat, {
      source: "url",
      zipcode: state.zip || null,
      updateUrl: true,
      fly: true,
    });
    return true;
  }
  return false;
}

export async function setLocationFromZipcode(zipcode, options = {}) {
  await Promise.all([loadZipcodes(), ensureMaster(), loadAxesConfig()]);
  const normalized = normalizeZipcode(zipcode);
  if (!normalized) {
    setStatus("Código postal inválido: usa 7 dígitos.");
    return false;
  }
  if (!_zipcodes || _zipcodes.status !== "ready") {
    setStatus("Sin tabla postal local; usa el monito en el mapa.");
    return false;
  }
  const record = (_zipcodes.records || []).find((r) => r.zipcode === normalized);
  if (!record) {
    setStatus(`ZIP ${normalized} no está en la referencia local.`);
    return false;
  }
  await setLocationPoint(record.lon, record.lat, {
    source: "zipcode",
    zipcode: normalized,
    updateUrl: options.updateUrl !== false,
    fly: options.fly !== false,
  });
  return true;
}

export async function setLocationPoint(lon, lat, options = {}) {
  await Promise.all([ensureMaster(), loadAxesConfig()]);
  const point = normalizePoint(lon, lat);
  if (!point) {
    setStatus("Coordenada inválida.");
    return null;
  }
  const commune = findCommuneAtPoint(point.lon, point.lat);
  if (!commune) {
    setStatus(`Punto fuera de ${getStudyManifest()?.location?.name || "la ciudad"}.`);
    return null;
  }
  _activePoint = {
    lon: point.lon,
    lat: point.lat,
    source: options.source || "manual",
    zipcode: options.zipcode || null,
    communeSlug: commune.properties.slug,
    communeName: commune.properties.name,
  };

  _widget.hidden = false;
  _card.hidden = false;
  _avatar.hidden = false;
  _pickMode = false;
  document.body.classList.remove("location-profile-pick-mode");
  updateAvatarPosition();
  if (options.fly !== false && _map) {
    _map.easeTo({
      center: [point.lon, point.lat],
      zoom: Math.max(_map.getZoom(), 11),
      duration: 650,
      essential: true,
    });
  }
  selectCommune(_activePoint.communeSlug);

  const profile = await computeLocationProfile(_activePoint, commune);
  renderLocationProfile(profile);
  setStatus(statusForPoint(_activePoint));

  const patch = {
    loc: formatLocationParam(point.lon, point.lat),
    zip: options.zipcode || null,
    commune: _activePoint.communeSlug,
  };
  if (options.updateUrl !== false) _updateState(patch);
  return profile;
}

export function clearLocationProfile() {
  _activePoint = null;
  _pickMode = false;
  document.body.classList.remove("location-profile-pick-mode");
  if (_avatar) _avatar.hidden = true;
  if (_card) _card.hidden = true;
  renderEmptyCard();
  setStatus("");
  _updateState({ loc: null, zip: null });
}

async function computeLocationProfile(point, communeFeature) {
  const axes = _axesConfig?.axes || [];
  const results = [];
  for (const axis of axes) {
    results.push(await computeAxis(axis, point, communeFeature));
  }
  const valid = results.filter((r) => Number.isFinite(r.score));
  const score = valid.length
    ? Math.round(valid.reduce((sum, r) => sum + r.score, 0) / valid.length)
    : null;
  return {
    point,
    score,
    validCount: valid.length,
    axes: results,
    methodNote: _axesConfig?.method_note || "",
  };
}

async function computeAxis(axis, point, communeFeature) {
  const palette = getPalette();
  const expo = palette.exposomes?.[axis.exposome] || {};
  const props = communeFeature.properties || {};

  if (
    axis.coverage_column
    && String(props[axis.coverage_column]) === String(axis.coverage_missing_value)
  ) {
    return missingAxis(axis, expo, "sin estimación");
  }

  let value = numeric(props[axis.column]);
  const spatial = studySpatialIndicator(axis.exposome);
  let support = mapSupportLabel(spatial, expo.resolution || "unidad administrativa");
  let supportLevel = "comuna";
  let distributionKey = `commune:${axis.column}`;
  let distribution = getCommuneDistribution(axis.column);

  // COG values are queried by the main map. This compact location card keeps
  // the old GeoJSON point lookup only when that exact compatibility asset is
  // published; it must never guess from a global palette flag.
  const detailAsset = studyDetailAsset(axis.exposome);
  if (axis.prefer_fine && studyHasFineLayer(axis.exposome) && detailAsset?.type === "geojson") {
    const fineData = await loadSubcomuna(axis.exposome);
    const fineFeature = fineData
      ? findSubcomunaFeatureAtPoint(fineData, point.lon, point.lat, point.communeSlug)
      : null;
    const fineValue = numeric(fineFeature?.properties?.value);
    if (Number.isFinite(fineValue)) {
      value = fineValue;
      support = spatial?.analysis?.label
        || spatial?.observation?.label
        || spatial?.downloaded?.label
        || (fineData?.native_resolution_m ? `≈${fineData.native_resolution_m} m` : "celda nativa");
      supportLevel = "celda";
      distributionKey = `fine:${axis.exposome}`;
      distribution = getFineDistribution(axis.exposome, fineData);
    }
  }

  if (!Number.isFinite(value) || !distribution.length) {
    return missingAxis(axis, expo, "sin dato");
  }

  const score = Math.round(rankPercentile(value, distribution, axis.direction) * 100);
  return {
    id: axis.id,
    label: axis.label,
    family: axis.family,
    rawValue: value,
    unit: expo.unit || "",
    score,
    support,
    supportLevel,
    direction: axis.direction,
    missing: false,
  };
}

function missingAxis(axis, expo, reason) {
  return {
    id: axis.id,
    label: axis.label,
    family: axis.family,
    rawValue: null,
    unit: expo.unit || "",
    score: null,
    support: reason,
    supportLevel: "missing",
    direction: axis.direction,
    missing: true,
  };
}

function renderLocationProfile(profile) {
  if (!_card || !profile) return;
  const score = Number.isFinite(profile.score) ? String(profile.score) : "--";
  const locationLabel = profile.point.zipcode
    ? `ZIP ${profile.point.zipcode}`
    : `${profile.point.lon.toFixed(4)}, ${profile.point.lat.toFixed(4)}`;
  _card.hidden = false;
  _card.innerHTML = `
    <div class="location-profile-card-header">
      <div>
        <h3 class="location-profile-card-title">Perfil local</h3>
        <p class="location-profile-card-meta">
          ${escHtml(locationLabel)} · ${escHtml(profile.point.communeName)}
        </p>
      </div>
      <div class="location-profile-score">
        <strong>${escHtml(score)}</strong>
        <span>carga rel.</span>
      </div>
    </div>
    ${renderRadar(profile.axes)}
    ${renderAxisTable(profile.axes)}
    <p class="location-profile-method-note">${escHtml(profile.methodNote)}</p>
  `;
}

// Fills the card's empty-state content without unhiding it: visibility is
// the caller's decision. Keeping the card hidden by default avoids a second
// instruction box competing with the commune-profile collapsible.
function renderEmptyCard() {
  if (!_card) return;
  _card.innerHTML = `
    <div class="location-profile-card-empty">
      Selecciona un punto del mapa o ingresa un código postal.
    </div>
  `;
}

function renderRadar(results) {
  const w = 270;
  const h = 240;
  const cx = 135;
  const cy = 118;
  const radius = 72;
  const n = results.length || 1;
  const angleFor = (i) => -Math.PI / 2 + (i / n) * Math.PI * 2;
  const pointFor = (i, valueScale = 1) => {
    const angle = angleFor(i);
    const r = radius * valueScale;
    return {
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
    };
  };
  const grid = [0.25, 0.5, 0.75, 1].map((level) => {
    const d = results.map((_, i) => {
      const p = pointFor(i, level);
      return `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
    }).join(" ") + " Z";
    return `<path class="location-radar-grid" d="${d}"></path>`;
  }).join("");
  const axes = results.map((r, i) => {
    const p = pointFor(i, 1);
    const lp = pointFor(i, 1.24);
    const anchor = lp.x < cx - 10 ? "end" : lp.x > cx + 10 ? "start" : "middle";
    return `
      <line class="location-radar-axis" x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}"></line>
      <text class="location-radar-label" x="${lp.x.toFixed(1)}" y="${lp.y.toFixed(1)}" text-anchor="${anchor}">
        ${escHtml(r.label)}
      </text>
    `;
  }).join("");
  const shape = results.map((r, i) => {
    const value = Number.isFinite(r.score) ? Math.max(0, Math.min(1, r.score / 100)) : 0;
    const p = pointFor(i, value);
    return `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
  }).join(" ") + " Z";
  const dots = results.map((r, i) => {
    const value = Number.isFinite(r.score) ? Math.max(0, Math.min(1, r.score / 100)) : 0;
    const p = pointFor(i, value);
    const cls = r.missing ? "location-radar-dot is-missing" : "location-radar-dot";
    return `<circle class="${cls}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4"></circle>`;
  }).join("");
  return `
    <svg class="location-radar" viewBox="0 0 ${w} ${h}" role="img" aria-label="Radar de perfil local">
      ${grid}
      ${axes}
      <path class="location-radar-shape" d="${shape}"></path>
      ${dots}
    </svg>
  `;
}

function renderAxisTable(results) {
  const rows = results.map((r) => {
    const value = Number.isFinite(r.rawValue)
      ? `${formatNumber(r.rawValue)} ${escHtml(r.unit)}`
      : escHtml(r.support);
    const score = Number.isFinite(r.score) ? `${r.score}` : "--";
    const cls = r.missing ? " class=\"is-missing\"" : "";
    return `
      <tr${cls}>
        <td>${escHtml(r.label)}</td>
        <td>${value}</td>
        <td>${score} · ${escHtml(r.supportLevel === "celda" ? r.support : "comuna")}</td>
      </tr>
    `;
  }).join("");
  return `<table class="location-profile-axis-table">${rows}</table>`;
}

function wireDom() {
  const form = document.getElementById("locationZipForm");
  const pick = document.getElementById("locationPickButton");
  const close = document.getElementById("locationCloseButton");
  if (form && form.dataset.wired !== "1") {
    form.dataset.wired = "1";
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      setLocationFromZipcode(_zipInput?.value || "");
    });
  }
  if (pick && pick.dataset.wired !== "1") {
    pick.dataset.wired = "1";
    pick.addEventListener("click", openLocationProfilePicker);
  }
  if (close && close.dataset.wired !== "1") {
    close.dataset.wired = "1";
    close.addEventListener("click", clearLocationProfile);
  }
  const toggle = document.getElementById("locationWidgetToggle");
  if (toggle && toggle.dataset.wired !== "1") {
    toggle.dataset.wired = "1";
    toggle.addEventListener("click", () => {
      const collapsed = !_widget?.classList.contains("is-collapsed");
      setWidgetCollapsed(collapsed);
      try { localStorage.setItem(WIDGET_COLLAPSE_KEY, collapsed ? "1" : "0"); } catch (_) {}
    });
  }
  if (_avatar && _avatar.dataset.wired !== "1") {
    _avatar.dataset.wired = "1";
    _avatar.addEventListener("pointerdown", startAvatarDrag);
  }
}

function setWidgetCollapsed(collapsed) {
  if (!_widget) return;
  _widget.classList.toggle("is-collapsed", collapsed);
  const toggle = document.getElementById("locationWidgetToggle");
  if (toggle) {
    toggle.textContent = collapsed ? "+" : "–";
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    toggle.setAttribute("aria-label", collapsed ? "Expandir" : "Minimizar");
    toggle.setAttribute("title", collapsed ? "Expandir" : "Minimizar");
  }
}

function applyPersistedCollapse() {
  let collapsed = false;
  try { collapsed = localStorage.getItem(WIDGET_COLLAPSE_KEY) === "1"; } catch (_) {}
  setWidgetCollapsed(collapsed);
}

function wireMap() {
  if (!_map) return;
  if (!_mapClickWired) {
    _map.on("click", handleMapClick);
    _mapClickWired = true;
  }
  if (!_mapMoveWired) {
    _map.on("move", updateAvatarPosition);
    _mapMoveWired = true;
  }
}

function handleMapClick(e) {
  if (!_pickMode || !_map) return;
  e.preventDefault?.();
  setLocationPoint(e.lngLat.lng, e.lngLat.lat, {
    source: "manual",
    zipcode: null,
    updateUrl: true,
    fly: false,
  });
}

function startAvatarDrag(e) {
  if (!_map || !_avatar || _avatar.hidden) return;
  _dragging = true;
  _pickMode = false;
  document.body.classList.remove("location-profile-pick-mode");
  _avatar.classList.add("is-dragging");
  _avatar.setPointerCapture?.(e.pointerId);
  e.preventDefault();
  document.addEventListener("pointermove", handleAvatarDrag);
  document.addEventListener("pointerup", stopAvatarDrag, { once: true });
}

function handleAvatarDrag(e) {
  if (!_dragging || !_map || !_avatar) return;
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  const rect = mapEl.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
  _avatar.style.left = `${x}px`;
  _avatar.style.top = `${y}px`;
}

function stopAvatarDrag(e) {
  document.removeEventListener("pointermove", handleAvatarDrag);
  if (!_dragging || !_map) return;
  _dragging = false;
  if (_avatar) _avatar.classList.remove("is-dragging");
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  const rect = mapEl.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
  const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
  const lngLat = _map.unproject([x, y]);
  setLocationPoint(lngLat.lng, lngLat.lat, {
    source: "manual",
    zipcode: null,
    updateUrl: true,
    fly: false,
  });
}

function updateAvatarPosition() {
  if (!_map || !_avatar || !_activePoint || _dragging) return;
  const p = _map.project([_activePoint.lon, _activePoint.lat]);
  _avatar.style.left = `${p.x}px`;
  _avatar.style.top = `${p.y}px`;
}

async function loadAxesConfig() {
  if (_axesConfig) return _axesConfig;
  const url = assetUrl("location_profile_axes.json") || "/data/location_profile_axes.json";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load location profile axes: ${res.status}`);
  _axesConfig = await res.json();
  return _axesConfig;
}

async function loadZipcodes() {
  if (_zipcodes) return _zipcodes;
  const res = await fetch(assetUrl("zipcodes.json") || "/data/zipcodes.json");
  // A dev server or SPA-rewrite host can answer a missing asset with a 200
  // OK index.html fallback instead of a real 404, so res.ok alone is not a
  // reliable "file exists" signal. Most study bundles have no zipcode table.
  const isJson = res.ok && (res.headers.get("content-type") || "").includes("json");
  if (!isJson) {
    _zipcodes = { status: "missing_reference", records: [] };
    return _zipcodes;
  }
  try {
    _zipcodes = await res.json();
  } catch {
    _zipcodes = { status: "missing_reference", records: [] };
  }
  return _zipcodes;
}

async function ensureMaster() {
  _master = getMaster();
  if (_master?.features?.length) return _master;
  const res = await fetch(assetUrl("master.geojson") || "/data/master.geojson");
  if (!res.ok) throw new Error(`Failed to load master.geojson: ${res.status}`);
  _master = await res.json();
  return _master;
}

async function loadSubcomuna(exposomeId) {
  const cacheKey = `${getSelectedStudyId() || "legacy"}:${exposomeId}`;
  if (_subcomunaCache.has(cacheKey)) return _subcomunaCache.get(cacheKey);
  const detail = studyDetailAsset(exposomeId);
  if (detail && detail.type !== "geojson") {
    _subcomunaCache.set(cacheKey, null);
    return null;
  }
  try {
    const res = await fetch(assetUrl(detail?.path || `subcomuna/${exposomeId}.geojson`) || `/data/subcomuna/${exposomeId}.geojson`);
    if (!res.ok) {
      _subcomunaCache.set(cacheKey, null);
      return null;
    }
    const data = await res.json();
    _subcomunaCache.set(cacheKey, data);
    return data;
  } catch (err) {
    console.warn(`loadSubcomuna(${exposomeId}) failed:`, err);
    _subcomunaCache.set(cacheKey, null);
    return null;
  }
}

function getCommuneDistribution(column) {
  const key = `commune:${column}`;
  if (_distributionCache.has(key)) return _distributionCache.get(key);
  const values = (_master?.features || [])
    .map((f) => numeric(f.properties?.[column]))
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  _distributionCache.set(key, values);
  return values;
}

function getFineDistribution(exposomeId, data) {
  const key = `fine:${exposomeId}`;
  if (_distributionCache.has(key)) return _distributionCache.get(key);
  const values = (data?.features || [])
    .map((f) => numeric(f.properties?.value))
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  _distributionCache.set(key, values);
  return values;
}

function findCommuneAtPoint(lon, lat) {
  return (_master?.features || []).find((feature) =>
    geometryContainsPoint(feature.geometry, lon, lat)
  ) || null;
}

function findSubcomunaFeatureAtPoint(data, lon, lat, communeSlug) {
  return (data?.features || []).find((feature) => {
    const props = feature.properties || {};
    if (communeSlug && props.commune_slug && props.commune_slug !== communeSlug) return false;
    return featureContainsPoint(feature, lon, lat);
  }) || null;
}

export function normalizeZipcode(value) {
  const digits = String(value || "").replace(/\D/g, "");
  return digits.length === 7 ? digits : null;
}

export function parseLocationParam(value) {
  if (!value || typeof value !== "string") return null;
  const [lonRaw, latRaw] = value.split(",");
  return normalizePoint(Number(lonRaw), Number(latRaw));
}

function normalizePoint(lon, lat) {
  const lonN = Number(lon);
  const latN = Number(lat);
  if (!Number.isFinite(lonN) || !Number.isFinite(latN)) return null;
  if (lonN < -180 || lonN > 180 || latN < -90 || latN > 90) return null;
  return { lon: lonN, lat: latN };
}

function formatLocationParam(lon, lat) {
  return `${Number(lon).toFixed(6)},${Number(lat).toFixed(6)}`;
}

export function rankPercentile(value, sortedValues, direction = 1) {
  if (!Number.isFinite(value) || !Array.isArray(sortedValues) || !sortedValues.length) {
    return 0.5;
  }
  let less = 0;
  let equal = 0;
  for (const v of sortedValues) {
    if (v < value) less += 1;
    else if (v === value) equal += 1;
    else break;
  }
  const rank = (less + equal / 2) / sortedValues.length;
  const oriented = direction === -1 ? 1 - rank : rank;
  return Math.max(0, Math.min(1, oriented));
}

function numeric(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function statusForPoint(point) {
  if (point.zipcode) return `ZIP ${point.zipcode} · ${point.communeName}`;
  return `Monito · ${point.communeName}`;
}

function setStatus(text) {
  if (_status) _status.textContent = text || "";
}

function formatNumber(value) {
  const abs = Math.abs(value);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
