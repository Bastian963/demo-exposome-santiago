// Download exposome values for a pasted list of points.
//
// The estimand is a block average over an explicit neighbourhood, never "the
// value at this address" (ADR 0012). Every number ships with the support it was
// measured over, and a radius that cannot resolve anything says so rather than
// looking precise.
//
// Panel-overlay pattern copied from analytics-compare.js: this module owns all
// of its innerHTML, and everything user-supplied goes through escHtml — pasted
// addresses are user input rendered back into a table.

import { getPalette } from "../palette.js";
import {
  dataUrl,
  getCatalog,
  loadCatalog,
} from "../data-repository.js";
import {
  KIND_ADDRESS,
  KIND_LATLON,
  KIND_POSTAL,
  POSTAL_PATTERNS,
  classifyLines,
} from "../utils/point-input.js";
import {
  deliveredSupportM,
  detailAssetFor,
  effectiveSupportM,
  radiusStatus,
  unavailableReason,
} from "../utils/detail-asset.js";
import { downloadText, serializeCSV } from "../utils/csv.js";
import { sampleIndicatorsAtPoint } from "../utils/cog-sample.js";
import { findFeatureAtPoint } from "../utils/geometry.js";

const DEFAULT_RADII = [0, 300, 500, 1000];

// Countries whose postal codes we can classify. None of them can be *resolved*
// yet: no postal reference is vendored, so the field explains itself instead of
// silently failing.
const POSTAL_COUNTRIES = Object.keys(POSTAL_PATTERNS).sort();
const POSTAL_GEOGRAPHY_NOTE = {
  CL: "Chile no publica un conjunto nacional de polígonos postales. Usa dirección o coordenadas.",
  PE: "En Perú el código postal apenas se usa; la geografía real es el distrito.",
  CO: "En Colombia el código postal apenas se usa; la geografía real es la localidad.",
  AR: "El CPA argentino no tiene polígonos abiertos. Usa dirección o coordenadas.",
  MX: "México sí tiene códigos postales reales, pero aún no vendorizamos la referencia.",
  BR: "Brasil sí tiene CEP real, pero aún no vendorizamos la referencia.",
  ES: "España sí tiene códigos postales reales, pero aún no vendorizamos la referencia.",
};

let _panel = null;
let _onBack = null;
let _resizeBound = false;
let _studies = [];
let _classified = [];
let _selectedIndicators = new Set();
let _radii = [...DEFAULT_RADII];
let _postalCountry = "";
let _results = null;
let _busy = false;
let _preflight = [];

export function initPointDownloadPanel(onBack) {
  _onBack = onBack;
  _panel = document.getElementById("pointDownloadPanel");
  if (!_panel) {
    console.warn("initPointDownloadPanel: #pointDownloadPanel not found");
    return;
  }
  if (!_resizeBound) {
    window.addEventListener("resize", positionUnderHeader);
    _resizeBound = true;
  }
}

export async function showPointDownloadPanel() {
  if (!_panel) return;
  _panel.hidden = false;
  _panel.classList.add("visible");
  document.body.classList.add("download-mode");
  positionUnderHeader();
  _panel.innerHTML = '<p class="pd-loading">Cargando catálogo…</p>';
  try {
    await loadCatalog();
    _studies = publishedStudies();
  } catch (error) {
    console.error("point-download: catalog failed", error);
    _panel.innerHTML =
      '<div class="pd-shell"><p class="pd-empty">No se pudo cargar el catálogo de ciudades.</p></div>';
    return;
  }
  render();
}

export function hidePointDownloadPanel() {
  if (!_panel) return;
  _panel.classList.remove("visible");
  _panel.hidden = true;
  document.body.classList.remove("download-mode");
}

export function isPointDownloadPanelVisible() {
  return _panel ? _panel.classList.contains("visible") && !_panel.hidden : false;
}

// The header is a CSS grid area with no fixed height; measure it so the
// fullscreen panel starts exactly below it.
function positionUnderHeader() {
  if (!_panel || _panel.hidden) return;
  const header = document.querySelector(".app-header");
  const top = header ? Math.round(header.getBoundingClientRect().bottom) : 0;
  _panel.style.top = `${top}px`;
}

// --- data ------------------------------------------------------------------

// Hidden studies are excluded: buenos_aires_comunas is hidden and has a smaller
// bbox than buenos_aires_amba, so including it would route a CABA address to
// the study with no detail COGs purely because its box is smaller.
function publishedStudies() {
  const catalog = getCatalog();
  return (catalog?.studies || [])
    .filter((study) => study.available && !study.hidden && Array.isArray(study.bbox))
    .map((study) => ({
      studyId: study.study_id,
      city: study.city,
      name: study.name,
      countryCode: study.country_code,
      bundle: study.bundle,
      bbox: study.bbox.map(Number),
      area: Math.abs(study.bbox[2] - study.bbox[0]) * Math.abs(study.bbox[3] - study.bbox[1]),
      manifest: null,
    }))
    // Smallest first, so a point inside both a metro and a city study resolves
    // to the finer one.
    .sort((a, b) => a.area - b.area);
}

function studyForPoint(lon, lat) {
  return _studies.find(
    (study) => lon >= study.bbox[0] && lon <= study.bbox[2]
      && lat >= study.bbox[1] && lat <= study.bbox[3],
  ) || null;
}

async function manifestFor(study) {
  if (study.manifest) return study.manifest;
  const response = await fetch(dataUrl(`${study.bundle}/manifest.json`));
  if (!response.ok) throw new Error(`manifest ${study.studyId}: ${response.status}`);
  study.manifest = await response.json();
  return study.manifest;
}

async function masterFor(study) {
  if (study.master) return study.master;
  const response = await fetch(dataUrl(`${study.bundle}/master.geojson`));
  if (!response.ok) throw new Error(`master ${study.studyId}: ${response.status}`);
  const geojson = await response.json();
  study.master = geojson.features || [];
  return study.master;
}

// --- rendering -------------------------------------------------------------

function render() {
  if (!_panel) return;
  _panel.innerHTML = `
    <div class="pd-shell">
      <header class="pd-header">
        <button type="button" class="pd-back" id="pdBack">← VOLVER</button>
        <h2 class="pd-title">DESCARGA POR PUNTO</h2>
        <span class="pd-subtitle">${_studies.length} ciudades publicadas</span>
      </header>
      <div class="pd-body">
        ${renderInputSection()}
        ${renderIndicatorSection()}
        ${renderRadiusSection()}
        ${renderRunSection()}
      </div>
    </div>`;
  bindEvents();
}

function renderInputSection() {
  const counts = summarize(_classified);
  const usable = counts.usable;
  return `
    <section class="pd-section">
      <h3 class="pd-section-title">1 · PUNTOS</h3>
      <p class="pd-hint">
        Una entrada por línea. Coordenadas <code>lat, lon</code> (con punto decimal),
        direcciones, o códigos postales con su país (<code>MX 06700</code>).
        Las coordenadas no salen de tu navegador.
      </p>
      <textarea id="pdInput" class="pd-textarea" rows="7"
        placeholder="-33.45, -70.65&#10;Manuel Rodriguez 1085, Maipu, Santiago, Chile&#10;CL 7500000"></textarea>
      <div class="pd-input-row">
        <label class="pd-file">
          <input type="file" id="pdFile" accept=".csv,.txt" hidden>
          <span>Cargar archivo…</span>
        </label>
        <label class="pd-country">
          País para códigos postales
          <select id="pdPostalCountry">
            <option value="">—</option>
            ${POSTAL_COUNTRIES.map((code) => `
              <option value="${code}" ${code === _postalCountry ? "selected" : ""}>${code}</option>
            `).join("")}
          </select>
        </label>
      </div>
      ${_classified.length ? `
        <div class="pd-summary">
          <strong>${usable}</strong> de ${_classified.length} líneas utilizables
          ${counts[KIND_POSTAL] ? ` · <span class="pd-warn">${counts[KIND_POSTAL]} código(s) postal(es) sin referencia</span>` : ""}
          ${counts[KIND_ADDRESS] ? ` · ${counts[KIND_ADDRESS]} dirección(es) requieren geocodificación` : ""}
        </div>
        <ul class="pd-lines">${_classified.map(renderLine).join("")}</ul>
      ` : ""}
    </section>`;
}

function renderLine(entry) {
  const badge = {
    [KIND_LATLON]: ["lat/lon", "ok"],
    [KIND_ADDRESS]: ["dirección", "pending"],
    [KIND_POSTAL]: ["código postal", "blocked"],
  }[entry.kind] || ["—", "blocked"];
  let note = "";
  if (entry.kind === KIND_POSTAL) {
    note = POSTAL_GEOGRAPHY_NOTE[entry.country] || "Sin referencia postal local.";
  } else if (entry.kind === KIND_ADDRESS) {
    note = entry.note || "Se geocodifica al extraer.";
  } else if (entry.kind === KIND_LATLON) {
    const study = studyForPoint(entry.lon, entry.lat);
    note = study ? study.name || study.city : "Fuera de toda ciudad publicada";
    if (!study) badge[1] = "blocked";
  }
  return `
    <li class="pd-line pd-line--${badge[1]}">
      <code class="pd-line-raw">${escHtml(entry.raw)}</code>
      <span class="pd-badge pd-badge--${badge[1]}">${badge[0]}</span>
      <span class="pd-line-note">${escHtml(note)}</span>
    </li>`;
}

function renderIndicatorSection() {
  const palette = getPalette();
  const exposomes = palette?.exposomes || {};
  const categories = { entorno: [], sociedad: [], resultados: [] };
  for (const [id, entry] of Object.entries(exposomes)) {
    if (entry.status !== "ready") continue;
    const bucket = categories[entry.category];
    if (bucket) bucket.push({ id, ...entry });
  }
  const groups = Object.entries(categories)
    .filter(([, items]) => items.length)
    .map(([category, items]) => `
      <div class="pd-cat">
        <h4 class="pd-cat-title">${category.toUpperCase()}
          <button type="button" class="pd-cat-all" data-category="${category}">todos</button>
        </h4>
        <div class="pd-chips">
          ${items.sort((a, b) => a.label.localeCompare(b.label)).map((item) => `
            <label class="pd-chip ${_selectedIndicators.has(item.id) ? "is-on" : ""}">
              <input type="checkbox" data-indicator="${escHtml(item.id)}"
                ${_selectedIndicators.has(item.id) ? "checked" : ""}>
              <span>${escHtml(item.label)}</span>
            </label>
          `).join("")}
        </div>
      </div>`).join("");
  return `
    <section class="pd-section">
      <h3 class="pd-section-title">2 · EXPOSOMAS
        <span class="pd-count">${_selectedIndicators.size} seleccionados</span>
      </h3>
      <p class="pd-hint">
        La disponibilidad real depende de cada ciudad y se resuelve al extraer:
        una capa sólo-Chile aparecerá como <code>country_not_supported</code> en Lima.
      </p>
      ${groups}
    </section>`;
}

function renderRadiusSection() {
  return `
    <section class="pd-section">
      <h3 class="pd-section-title">3 · RADIOS</h3>
      <p class="pd-hint">
        Esta pestaña entrega <strong>la celda que contiene el punto</strong>: el valor
        publicado, sin modelo. Es el número primario y el que coincide exactamente
        con el que da el CLI.
      </p>
      <p class="pd-hint">
        Los promedios sobre un disco (300 / 500 / 1000 m) requieren leer una ventana
        completa del ráster y ponderar cada celda por el área que cae dentro. Eso lo
        hace el CLI; el navegador no lo aproxima, porque una aproximación distinta
        daría <em>otro número</em> para la misma dirección según por dónde se pidió.
      </p>
      <label class="pd-radii-label">
        Radios para el comando
        <input type="text" id="pdRadii" class="pd-radii" value="${_radii.join(", ")}">
      </label>
      ${renderRadiusPreflight()}
      <div class="pd-cli">
        <code id="pdCliCommand">${escHtml(cliCommand())}</code>
        <button type="button" id="pdCopyCli" class="pd-download">Copiar comando</button>
      </div>
    </section>`;
}

// Preflight: which of the requested radii would resolve anything, per selected
// indicator. Read from the manifests, no pixels involved.
function renderRadiusPreflight() {
  if (!_selectedIndicators.size || !_preflight.length) return "";
  return `
    <div class="pd-table-wrap">
      <table class="pd-table pd-table--compact">
        <thead><tr>
          <th>ciudad</th><th>exposoma</th><th>soporte</th>
          ${_radii.map((r) => `<th>${r === 0 ? "celda" : `${r} m`}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${_preflight.map((row) => `
            <tr>
              <td>${escHtml(row.city)}</td>
              <td>${escHtml(row.indicatorId)}</td>
              <td>${row.support === null ? "—" : `${Math.round(row.support)} m`}</td>
              ${row.statuses.map((status) => `
                <td class="pd-cell--${status}">${
                  { resolved: "✓", sub_observation: "sub", not_applicable: "—" }[status] || status
                }</td>`).join("")}
            </tr>`).join("")}
        </tbody>
      </table>
      <p class="pd-hint pd-hint--small">
        <code>sub</code> = el disco es menor que el soporte de la capa: se entrega igual,
        marcado, pero no promedia nada. NO₂ está así en todos los radios porque una
        observación TROPOMI cubre 3,5 × 5,5–7 km.
      </p>
    </div>`;
}

function cliCommand() {
  const indicators = [..._selectedIndicators].join(",") || "pm25";
  return `exposome extract-points --input puntos.csv --indicators ${indicators} `
    + `--radii ${_radii.join(",")} --output out/`;
}

function renderRunSection() {
  const counts = summarize(_classified);
  const ready = counts.usable > 0 && _selectedIndicators.size > 0 && !_busy;
  return `
    <section class="pd-section">
      <h3 class="pd-section-title">4 · EXTRAER</h3>
      <button type="button" id="pdRun" class="pd-run" ${ready ? "" : "disabled"}>
        ${_busy ? "EXTRAYENDO…" : "EXTRAER Y DESCARGAR"}
      </button>
      <div id="pdStatus" class="pd-status"></div>
      ${_results ? renderResults() : ""}
    </section>`;
}

function renderResults() {
  const rows = _results.rows;
  const withValue = rows.filter((row) => row.value !== null && row.value !== undefined).length;
  const subObs = rows.filter((row) => row.radius_status === "sub_observation").length;
  const preview = rows.slice(0, 40);
  return `
    <div class="pd-results">
      <div class="pd-results-summary">
        <strong>${rows.length}</strong> filas · ${withValue} con valor ·
        ${subObs} <code>sub_observation</code>
        <button type="button" id="pdCsv" class="pd-download">Descargar CSV largo</button>
        <button type="button" id="pdCsvWide" class="pd-download">CSV ancho</button>
      </div>
      <div class="pd-table-wrap">
        <table class="pd-table">
          <thead><tr>
            <th>punto</th><th>ciudad</th><th>exposoma</th><th>radio</th>
            <th>valor</th><th>sd</th><th>soporte</th><th>estado</th>
          </tr></thead>
          <tbody>
            ${preview.map((row) => `
              <tr class="pd-row--${escHtml(row.quality_flag)}">
                <td>${escHtml(row.query_id)}</td>
                <td>${escHtml(row.city || "—")}</td>
                <td>${escHtml(row.exposome_id)}</td>
                <td>${row.radius_m === null ? "—" : row.radius_m}</td>
                <td>${fmt(row.value)}</td>
                <td>${fmt(row.sd_within_buffer)}</td>
                <td>${fmt(row.support_m, 0)}</td>
                <td>${escHtml(row.quality_flag)}</td>
              </tr>`).join("")}
          </tbody>
        </table>
        ${rows.length > preview.length
          ? `<p class="pd-hint">Mostrando ${preview.length} de ${rows.length} filas; el CSV las trae todas.</p>`
          : ""}
      </div>
    </div>`;
}

// --- events ----------------------------------------------------------------

function bindEvents() {
  byId("pdBack")?.addEventListener("click", () => {
    hidePointDownloadPanel();
    if (_onBack) _onBack();
  });
  byId("pdInput")?.addEventListener("input", (event) => {
    _classified = classifyLines(event.target.value, _postalCountry || null);
    rerenderInputAndRun(event.target.value);
    refreshPreflight();
  });
  byId("pdPostalCountry")?.addEventListener("change", (event) => {
    _postalCountry = event.target.value;
    const text = byId("pdInput")?.value || "";
    _classified = classifyLines(text, _postalCountry || null);
    rerenderInputAndRun(text);
  });
  byId("pdFile")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const input = byId("pdInput");
    if (input) input.value = text;
    _classified = classifyLines(text, _postalCountry || null);
    rerenderInputAndRun(text);
  });
  byId("pdRadii")?.addEventListener("change", (event) => {
    const parsed = event.target.value
      .split(/[,\s]+/)
      .map((token) => Number(token))
      .filter((value) => Number.isFinite(value) && value >= 0);
    _radii = parsed.length ? parsed : [...DEFAULT_RADII];
    render();
    refreshPreflight();
  });
  _panel.querySelectorAll("[data-indicator]").forEach((box) => {
    box.addEventListener("change", (event) => {
      const id = event.target.dataset.indicator;
      if (event.target.checked) _selectedIndicators.add(id);
      else _selectedIndicators.delete(id);
      render();
      refreshPreflight();
    });
  });
  _panel.querySelectorAll(".pd-cat-all").forEach((button) => {
    button.addEventListener("click", (event) => {
      const category = event.target.dataset.category;
      const palette = getPalette();
      for (const [id, entry] of Object.entries(palette?.exposomes || {})) {
        if (entry.category === category && entry.status === "ready") _selectedIndicators.add(id);
      }
      render();
    });
  });
  byId("pdCopyCli")?.addEventListener("click", async (event) => {
    try {
      await navigator.clipboard.writeText(cliCommand());
      event.target.textContent = "¡Copiado!";
      setTimeout(() => { event.target.textContent = "Copiar comando"; }, 1500);
    } catch { /* clipboard blocked; the command is on screen anyway */ }
  });
  byId("pdRun")?.addEventListener("click", runExtraction);
  byId("pdCsv")?.addEventListener("click", () => {
    downloadText("point_exposome_long.csv", serializeCSV(_results.rows));
  });
  byId("pdCsvWide")?.addEventListener("click", () => {
    downloadText("point_exposome_wide.csv", serializeCSV(toWide(_results.rows)));
  });
}

// Which (city, indicator, radius) combinations would resolve anything. Reads
// manifests only, so it can answer before a single pixel is fetched.
async function refreshPreflight() {
  const cities = new Map();
  for (const entry of _classified) {
    if (entry.kind !== KIND_LATLON) continue;
    const study = studyForPoint(entry.lon, entry.lat);
    if (study) cities.set(study.studyId, study);
  }
  const rows = [];
  for (const study of cities.values()) {
    let manifest;
    try {
      manifest = await manifestFor(study);
    } catch {
      continue;
    }
    for (const indicatorId of _selectedIndicators) {
      const record = manifest.spatial_indicators?.[indicatorId];
      const blocked = unavailableReason(manifest, indicatorId);
      const support = blocked ? null : effectiveSupportM(record);
      rows.push({
        city: study.city,
        indicatorId,
        support,
        statuses: _radii.map((radius) => (
          blocked ? "not_applicable" : radiusStatus(support, radius)
        )),
      });
    }
  }
  _preflight = rows;
  const host = _panel?.querySelector(".pd-section:nth-of-type(3) .pd-table-wrap");
  if (host) host.outerHTML = renderRadiusPreflight();
}

// Re-render only what depends on the input, so typing does not steal focus.
function rerenderInputAndRun(text) {
  render();
  const input = byId("pdInput");
  if (input) {
    input.value = text;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
}

// --- extraction ------------------------------------------------------------

async function runExtraction() {
  const usable = _classified.filter((entry) => entry.kind === KIND_LATLON);
  if (!usable.length) {
    setStatus("Ninguna línea utilizable. Por ahora sólo se extraen coordenadas.");
    return;
  }
  _busy = true;
  render();
  const rows = [];
  try {
    for (let i = 0; i < usable.length; i++) {
      const entry = usable[i];
      setStatus(`Extrayendo punto ${i + 1} de ${usable.length}…`);
      rows.push(...await extractPoint(entry));
    }
    _results = { rows };
    setStatus("");
  } catch (error) {
    console.error("point-download: extraction failed", error);
    setStatus(`Falló la extracción: ${error.message}`);
  } finally {
    _busy = false;
    render();
  }
}

async function extractPoint(entry) {
  const study = studyForPoint(entry.lon, entry.lat);
  const base = {
    query_id: entry.queryId,
    input_raw: entry.raw,
    input_kind: entry.kind,
    lon: entry.lon,
    lat: entry.lat,
    geocode_precision: "latlon_exact",
    geocode_accuracy_m: 0,
  };
  if (!study) {
    return [{ ...base, study_id: null, city: null, exposome_id: null,
      radius_m: null, value: null, quality_flag: "out_of_coverage" }];
  }
  const manifest = await manifestFor(study);
  const palette = getPalette();
  const rows = [];

  for (const indicatorId of _selectedIndicators) {
    const record = manifest.spatial_indicators?.[indicatorId];
    const meta = palette?.exposomes?.[indicatorId] || {};
    const common = {
      ...base,
      study_id: study.studyId,
      city: study.city,
      country_code: study.countryCode,
      exposome_id: indicatorId,
      label: meta.label || null,
      unit: meta.unit || null,
    };

    // The study's own declaration wins: a Chile-only layer says why it is
    // missing in Lima rather than surfacing as an absent column.
    const blocked = unavailableReason(manifest, indicatorId);
    if (blocked) {
      rows.push({ ...common, radius_m: null, value: null,
        unavailable_reason: blocked, quality_flag: "not_published_by_study" });
      continue;
    }

    const asset = detailAssetFor(manifest, indicatorId);
    if (!asset || asset.type !== "cog") {
      // Either administrative-only, or a fine polygon layer like `green` whose
      // detail is subcomuna/green.geojson rather than a raster.
      rows.push(await administrativeRow(study, manifest, indicatorId, common, meta));
      continue;
    }

    const support = effectiveSupportM(record);
    const [sample] = await sampleIndicatorsAtPoint(
      [{ url: `${location.origin}${dataUrl(`${study.bundle}/${asset.path}`)}`, band: asset.band || 1 }],
      { longitude: entry.lon, latitude: entry.lat },
    );
    // Radius 0 only. The browser reads the containing native pixel; an
    // area-weighted disc needs the whole window and the CLI computes it
    // exactly. Emitting a radius_m of 300 next to a single-pixel value would
    // imply an average that was never taken.
    rows.push({
      ...common,
      estimand_kind: "raster_block",
      radius_m: 0,
      radius_status: radiusStatus(support, 0),
      value: sample.value,
      // No buffer, so no within-buffer spread exists to report.
      sd_within_buffer: null,
      n_cells: sample.value === null ? 0 : 1,
      support_m: deliveredSupportM(support, 0),
      observation_support_m: support,
      source_asset: asset.path,
      quality_flag: sample.value === null ? "no_data" : radiusStatus(support, 0),
    });
  }
  return rows;
}

async function administrativeRow(study, manifest, indicatorId, common, meta) {
  const features = await masterFor(study);
  const feature = findFeatureAtPoint(features, common.lon, common.lat);
  const column = meta.column;
  const value = feature && column ? feature.properties?.[column] : null;
  return {
    ...common,
    estimand_kind: "administrative_unit",
    // An administrative value has no radius: averaging across units produces a
    // number that exists in neither of them (ADR 0004 §5).
    radius_m: null,
    radius_status: "not_applicable",
    value: value === undefined ? null : value,
    sd_within_buffer: null,
    support_m: null,
    spatial_id: feature?.properties?.spatial_id ?? null,
    spatial_name: feature?.properties?.spatial_name ?? null,
    source_asset: "master.geojson",
    quality_flag: value === null || value === undefined ? "no_data" : "ok",
  };
}

function toWide(rows) {
  const byPoint = new Map();
  for (const row of rows) {
    if (row.radius_m !== null && row.radius_m !== 0) continue;
    const key = row.query_id;
    if (!byPoint.has(key)) {
      byPoint.set(key, {
        query_id: row.query_id, input_raw: row.input_raw,
        lon: row.lon, lat: row.lat, study_id: row.study_id,
      });
    }
    if (row.exposome_id) byPoint.get(key)[row.exposome_id] = row.value;
  }
  return [...byPoint.values()];
}

// --- helpers ---------------------------------------------------------------

function summarize(entries) {
  const counts = { [KIND_LATLON]: 0, [KIND_ADDRESS]: 0, [KIND_POSTAL]: 0, usable: 0 };
  for (const entry of entries) {
    if (counts[entry.kind] !== undefined) counts[entry.kind] += 1;
    if (entry.kind === KIND_LATLON && studyForPoint(entry.lon, entry.lat)) counts.usable += 1;
  }
  return counts;
}

function setStatus(message) {
  const node = byId("pdStatus");
  if (node) node.textContent = message;
}

function byId(id) {
  return _panel ? _panel.querySelector(`#${id}`) : null;
}

function fmt(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : String(value);
}

function escHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
