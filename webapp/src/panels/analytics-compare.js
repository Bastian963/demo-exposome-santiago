// ANALYTICS panel: cross-city distribution comparison, reachable only from
// the LATAM globe (the only screen where more than one city coexists).
//
// Everything statistical (robust median/MAD band, shared histogram bins, log
// bins, eCDF points, KS, k-sample Anderson-Darling) is precomputed by
// scripts/export_webapp_distributions.py -- this module only renders the
// resulting webapp/public/data/v1/analytics/distributions.json and, in log
// mode, applies a purely visual log10 remap (never a re-computed statistic).
// See docs/analytics_distribution_comparison.md for the methodology.

import { loadDistributions } from "../data-repository.js";
import { getPalette } from "../palette.js";

const FALLBACK_COLORS = ["#3fb28f", "#e0a340", "#c75c9b", "#5c8fd6", "#e0574a", "#7fd68a"];

// The rail mirrors the CITY_OVERVIEW picker exactly: the same palette.exposomes
// catalog, grouped by the same 3 categories, in palette order. We never invent
// a taxonomy here -- an exposome is selectable iff a precomputed distribution
// exists for its id (or, for a group like Calor/Lluvia, one of its children).
const CATEGORY_ORDER = ["entorno", "sociedad", "resultados"];
// Headings render in Press Start 2P (uppercase) -- sin tildes a proposito.
const CATEGORY_META = {
  entorno: { title: "NATURALES", subtitle: "Exposoma fisico-ambiental" },
  sociedad: { title: "SOCIALES", subtitle: "Contexto socioeconomico y redes" },
  resultados: { title: "RESULTADOS", subtitle: "Mapas ecologicos" },
};

const CHART_W = 460;
const CHART_H = 240;
const MARGIN = { left: 34, right: 12, top: 14, bottom: 30 };

let _panel = null;
let _onBack = null;
let _data = null;
let _activeTab = "comparar";
let _activeIndicatorId = null;
let _railGroupId = null;
let _searchQuery = "";
let _logScale = false;
let _selectedCities = new Set();
let _cityColorBySlug = new Map();
let _resizeBound = false;

export function initAnalyticsPanel(onBack) {
  _onBack = onBack;
  _panel = document.getElementById("analyticsPanel");
  if (!_panel) {
    console.warn("initAnalyticsPanel: #analyticsPanel not found");
    return;
  }
  if (!_resizeBound) {
    window.addEventListener("resize", positionUnderHeader);
    _resizeBound = true;
  }
}

export async function showAnalyticsPanel() {
  if (!_panel) return;
  _panel.hidden = false;
  _panel.classList.add("visible");
  positionUnderHeader();
  _panel.innerHTML = '<p class="analytics-loading">Cargando distribuciones...</p>';
  try {
    _data = await loadDistributions();
  } catch (err) {
    console.error("Failed to load distributions:", err);
    _panel.innerHTML =
      '<div class="analytics-shell"><p class="analytics-empty">No se pudo cargar la comparacion entre ciudades.</p></div>';
    return;
  }
  assignCityColors(_data.cities || []);
  if (!_selectedCities.size) {
    _selectedCities = new Set((_data.cities || []).map((c) => c.slug));
  }
  if (!_activeIndicatorId || !_data.indicators?.[_activeIndicatorId]) {
    _activeIndicatorId = firstIndicatorId(_data);
  }
  _railGroupId = null;
  _logScale = false;
  renderShell();
}

export function hideAnalyticsPanel() {
  if (!_panel) return;
  _panel.classList.remove("visible");
  _panel.hidden = true;
}

export function isAnalyticsPanelVisible() {
  return _panel ? _panel.classList.contains("visible") && !_panel.hidden : false;
}

// The GEMMA header is a CSS grid area with no fixed height; measure it so the
// fullscreen panel starts exactly below it (and re-measure on resize).
function positionUnderHeader() {
  if (!_panel || _panel.hidden) return;
  const header = document.querySelector(".app-header");
  const top = header ? Math.round(header.getBoundingClientRect().bottom) : 0;
  _panel.style.top = `${top}px`;
}

function assignCityColors(cities) {
  const palette = getPalette();
  const ramp = palette?.data_colormaps?.categorical?.length
    ? palette.data_colormaps.categorical
    : FALLBACK_COLORS;
  _cityColorBySlug = new Map();
  // Sorted by slug (not catalog order) so a city's color never shifts as more
  // cities are published -- Santiago and Buenos Aires keep the same color.
  [...cities.map((c) => c.slug)].sort().forEach((slug, index) => {
    _cityColorBySlug.set(slug, ramp[index % ramp.length]);
  });
}

function cityColor(slug) {
  return _cityColorBySlug.get(slug) || "#94b0c2";
}

function cityName(slug) {
  return (_data?.cities || []).find((c) => c.slug === slug)?.name || slug;
}

function firstIndicatorId(data) {
  const ids = Object.keys(data?.indicators || {});
  return ids.includes("pm25") ? "pm25" : ids[0] || null;
}

// ---- shell / tabs ---------------------------------------------------------

function renderShell() {
  _panel.innerHTML = `
    <div class="analytics-shell">
      <div class="analytics-header">
        <button class="city-panel-back" id="analyticsPanelBack" type="button">&larr; MUNDO</button>
        <h2 class="analytics-title">ANALYTICS</h2>
        <div class="analytics-tabs" role="tablist">
          <button class="analytics-tab" role="tab" data-tab="comparar" aria-selected="${_activeTab === "comparar"}" type="button">COMPARAR</button>
          <button class="analytics-tab" role="tab" data-tab="metodo" aria-selected="${_activeTab === "metodo"}" type="button">METODO</button>
        </div>
      </div>
      <div class="analytics-content" id="analyticsContent"></div>
    </div>
  `;
  _panel.querySelector("#analyticsPanelBack").addEventListener("click", () => {
    hideAnalyticsPanel();
    if (_onBack) _onBack();
  });
  _panel.querySelectorAll(".analytics-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      _activeTab = btn.dataset.tab;
      renderShell();
    });
  });
  const content = _panel.querySelector("#analyticsContent");
  if (_activeTab === "metodo") {
    content.innerHTML = renderMethodology();
    content.scrollTop = 0;
  } else {
    renderCompare(content);
  }
}

function renderCompare(content) {
  const indicatorCount = Object.keys(_data.indicators || {}).length;
  if (!indicatorCount) {
    content.innerHTML = '<p class="analytics-empty">Todavia no hay indicadores comparables publicados.</p>';
    return;
  }
  content.innerHTML = `
    <aside class="analytics-sidebar">
      <label class="analytics-search-label" for="analyticsSearch">Buscar exposoma</label>
      <input id="analyticsSearch" class="analytics-search" type="search"
             placeholder="pm2.5, calor, salud..." value="${escHtml(_searchQuery)}"
             autocomplete="off" spellcheck="false" />
      <div class="analytics-rail" id="analyticsRail">${renderRail()}</div>
    </aside>
    <section class="analytics-main" id="analyticsMain">${renderMain()}</section>
  `;
  wireSidebar();
  wireMain();
}

// ---- sidebar: exposome catalog rail (mirrors CITY_OVERVIEW picker) ---------

function exposomeCatalog() {
  return getPalette()?.exposomes || {};
}

function childIds(entry) {
  if (!entry) return [];
  if (Array.isArray(entry.children) && entry.children.length) return entry.children;
  if (!entry.id) return [];
  const catalog = exposomeCatalog();
  return Object.keys(catalog).filter((cid) => catalog[cid].parent === entry.id);
}

function isGroup(entry) {
  return entry?.status === "group" || childIds(entry).length > 0;
}

// The indicator id that actually carries data for a catalog card: a leaf maps
// to itself; a group maps to its first child that has a distribution. Returns
// null when nothing under the card is cross-city comparable ("sin datos").
function dataIdFor(entry) {
  if (!entry) return null;
  if (_data.indicators?.[entry.id]) return entry.id;
  for (const cid of childIds(entry)) {
    if (_data.indicators?.[cid]) return cid;
  }
  return null;
}

function normalize(text) {
  return String(text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

// Top-level catalog cards per category, in palette order, with children
// collapsed under their group -- exactly like city-overview's renderMainContent.
function topLevelByCategory() {
  const catalog = exposomeCatalog();
  const groups = { entorno: [], sociedad: [], resultados: [] };
  for (const [id, e] of Object.entries(catalog)) {
    if (e.parent) continue;
    const cat = e.category || "entorno";
    (groups[cat] ||= []).push({ id, ...e });
  }
  return groups;
}

function renderRail() {
  if (_searchQuery.trim()) return renderRailSearch();
  if (_railGroupId) return renderRailGroup(_railGroupId);
  return renderRailCategories();
}

function renderRailCategories() {
  const groups = topLevelByCategory();
  return CATEGORY_ORDER.map((cat) => {
    const items = groups[cat] || [];
    if (!items.length) return "";
    const meta = CATEGORY_META[cat] || { title: cat, subtitle: "" };
    return `
      <div class="analytics-rail-group" data-category="${cat}">
        <h3 class="analytics-rail-heading">${escHtml(meta.title)}</h3>
        <p class="analytics-rail-sub">${escHtml(meta.subtitle)}</p>
        <div class="analytics-rail-cards">${items.map(renderRailCard).join("")}</div>
      </div>
    `;
  }).join("");
}

function renderRailGroup(groupId) {
  const catalog = exposomeCatalog();
  const group = catalog[groupId] ? { id: groupId, ...catalog[groupId] } : null;
  const kids = childIds(group)
    .map((cid) => (catalog[cid] ? { id: cid, ...catalog[cid] } : null))
    .filter(Boolean);
  return `
    <div class="analytics-rail-group">
      <button class="analytics-rail-back" id="analyticsRailBack" type="button">&larr; EXPOSOMAS</button>
      <h3 class="analytics-rail-heading">${escHtml(group?.label || groupId)}</h3>
      <div class="analytics-rail-cards">${
        kids.length ? kids.map(renderRailCard).join("") : '<p class="analytics-variants-empty">Sin subexposomas.</p>'
      }</div>
    </div>
  `;
}

function renderRailSearch() {
  const q = normalize(_searchQuery);
  const catalog = exposomeCatalog();
  // Search flattens groups: match leaves (and group children) by label / id /
  // category name -- group parents themselves are skipped, their children shown.
  const matches = Object.entries(catalog)
    .map(([id, e]) => ({ id, ...e }))
    .filter((e) => !isGroup(e))
    .filter(
      (e) =>
        normalize(e.label).includes(q) ||
        normalize(e.id).includes(q) ||
        normalize(CATEGORY_META[e.category]?.title || e.category).includes(q),
    );
  if (!matches.length) return '<p class="analytics-variants-empty">Sin coincidencias.</p>';
  return `<div class="analytics-rail-group"><div class="analytics-rail-cards">${matches
    .map(renderRailCard)
    .join("")}</div></div>`;
}

function renderRailCard(e) {
  const group = isGroup(e);
  const dataId = dataIdFor(e);
  const comparable = Boolean(dataId);
  const entry = comparable ? _data.indicators[dataId] : null;
  const active =
    comparable && (dataId === _activeIndicatorId || (group && childIds(e).includes(_activeIndicatorId)));
  const iconId = e.icon_key || e.parent || e.id;
  let badge;
  let badgeClass;
  if (group) {
    const kids = childIds(e);
    const n = kids.filter((cid) => _data.indicators?.[cid]).length;
    badge = `${n}/${kids.length}`;
    badgeClass = "analytics-badge-group";
  } else if (comparable) {
    badge = entry.sample_level === "fine" ? "FINA" : "ADMIN";
    badgeClass = entry.sample_level === "fine" ? "analytics-badge-fine" : "analytics-badge-admin";
  } else {
    badge = "sin datos";
    badgeClass = "analytics-badge-empty";
  }
  const cls = ["analytics-expo"];
  if (active) cls.push("is-active");
  if (!comparable) cls.push("is-disabled");
  if (group) cls.push("is-group");
  return `
    <button class="${cls.join(" ")}" type="button"
            data-card="${escHtml(e.id)}"
            data-group="${group ? "1" : "0"}"
            data-indicator="${escHtml(dataId || "")}"
            aria-pressed="${active}"
            ${comparable ? "" : 'aria-disabled="true"'}
            title="${comparable ? escHtml(e.label) : "sin datos comparables"}">
      <span class="exposome-card-icon icon-${escHtml(iconId)}" aria-hidden="true"></span>
      <span class="analytics-expo-name">${escHtml(e.label)}</span>
      <span class="analytics-badge ${badgeClass}">${escHtml(badge)}</span>
    </button>
  `;
}

function wireSidebar() {
  const search = _panel.querySelector("#analyticsSearch");
  search?.addEventListener("input", (e) => {
    _searchQuery = e.target.value;
    refreshRail();
  });
  search?.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      _searchQuery = "";
      e.target.value = "";
      refreshRail();
    }
  });
  wireRail();
}

function wireRail() {
  _panel.querySelector("#analyticsRailBack")?.addEventListener("click", () => {
    _railGroupId = null;
    refreshRail();
  });
  _panel.querySelectorAll(".analytics-expo").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.getAttribute("aria-disabled") === "true") return;
      const cardId = btn.dataset.card;
      const catalog = exposomeCatalog();
      const entry = catalog[cardId] ? { id: cardId, ...catalog[cardId] } : null;
      // A group with real children drills in; a leaf (or a searched card) selects.
      if (btn.dataset.group === "1" && !_searchQuery.trim() && childIds(entry).length) {
        _railGroupId = cardId;
        refreshRail();
        return;
      }
      const dataId = btn.dataset.indicator;
      if (!dataId) return;
      _activeIndicatorId = dataId;
      _logScale = false;
      refreshMain();
      refreshRailActive();
    });
  });
}

function refreshRail() {
  const box = _panel.querySelector("#analyticsRail");
  if (box) {
    box.innerHTML = renderRail();
    wireRail();
  }
}

function refreshRailActive() {
  const catalog = exposomeCatalog();
  _panel.querySelectorAll(".analytics-expo").forEach((btn) => {
    const entry = catalog[btn.dataset.card] ? { id: btn.dataset.card, ...catalog[btn.dataset.card] } : null;
    const on =
      btn.dataset.indicator === _activeIndicatorId ||
      (btn.dataset.group === "1" && childIds(entry).includes(_activeIndicatorId));
    btn.classList.toggle("is-active", Boolean(on));
    btn.setAttribute("aria-pressed", String(Boolean(on)));
  });
}

function refreshMain() {
  const box = _panel.querySelector("#analyticsMain");
  if (box) {
    box.innerHTML = renderMain();
    wireMain();
  }
}

// ---- main: meta + city chips + charts + readout ---------------------------

function renderMain() {
  const entry = _data.indicators[_activeIndicatorId];
  if (!entry) return '<p class="analytics-empty">Selecciona un indicador.</p>';
  const cityIds = Object.keys(entry.cities).filter((slug) => _selectedCities.has(slug));
  return `
    ${renderIndicatorMeta(entry)}
    ${renderCityChips(entry)}
    ${cityIds.length ? renderChartArea(entry, cityIds) : '<p class="analytics-empty">Selecciona al menos una ciudad con datos.</p>'}
  `;
}

function renderIndicatorMeta(entry) {
  const badgeClass = entry.sample_level === "fine" ? "analytics-badge-fine" : "analytics-badge-admin";
  const badgeText = entry.sample_level === "fine" ? "FINA" : "ADMIN";
  const unit = entry.unit ? escHtml(entry.unit) : "sin unidad registrada";
  const unitTitle = entry.unit_long ? ` title="${escHtml(entry.unit_long)}"` : "";
  return `
    <div class="analytics-indicator-meta">
      <span class="analytics-badge ${badgeClass}">${badgeText}</span>
      <span class="analytics-indicator-label">${escHtml(entry.label)}</span>
      <span class="analytics-indicator-unit"${unitTitle}>${unit}</span>
      <span class="analytics-indicator-resolution">${escHtml(entry.resolution || "")}</span>
    </div>
  `;
}

function renderCityChips(entry) {
  const chips = (_data.cities || [])
    .map((c) => {
      const hasData = Boolean(entry.cities[c.slug]);
      const selected = _selectedCities.has(c.slug) && hasData;
      return `
        <button class="analytics-chip ${selected ? "is-on" : ""}" type="button"
                data-city="${escHtml(c.slug)}" aria-pressed="${selected}" ${hasData ? "" : "disabled"}>
          <span class="analytics-chip-swatch" style="background:${cityColor(c.slug)}"></span>
          ${escHtml(c.name)}<span class="analytics-chip-cc">${escHtml(c.country_code || "")}</span>
        </button>
      `;
    })
    .join("");
  return `<div class="analytics-chips" role="group" aria-label="Ciudades">${chips}</div>`;
}

function renderChartArea(entry, cityIds) {
  const canLog = Boolean(entry.log);
  const logToggle = canLog
    ? `<label class="analytics-log-toggle">
         <input type="checkbox" id="analyticsLog" ${_logScale ? "checked" : ""} /> Escala log (eje X)
       </label>`
    : `<span class="analytics-log-hint" title="Requiere que todos los valores sean &gt; 0">escala log no disponible</span>`;
  return `
    <div class="analytics-chart-controls">${logToggle}</div>
    <div class="analytics-chart-row">
      <figure class="analytics-chart">
        <figcaption>HISTOGRAMA</figcaption>
        ${renderHistogram(entry, cityIds)}
      </figure>
      <figure class="analytics-chart">
        <figcaption>CURVA ACUMULADA</figcaption>
        ${renderEcdf(entry, cityIds)}
      </figure>
    </div>
    ${renderReadout(entry, cityIds)}
  `;
}

function wireMain() {
  _panel.querySelectorAll(".analytics-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const slug = btn.dataset.city;
      if (_selectedCities.has(slug)) _selectedCities.delete(slug);
      else _selectedCities.add(slug);
      refreshMain();
    });
  });
  const log = _panel.querySelector("#analyticsLog");
  log?.addEventListener("change", () => {
    _logScale = log.checked;
    refreshMain();
  });
}

// ---- scale context (linear or visual log10) -------------------------------

function scaleContext(entry, cityIds) {
  const useLog = _logScale && Boolean(entry.log);
  const bins = useLog ? entry.log.bins : entry.bins;
  const lo = bins[0];
  const hi = bins[bins.length - 1];
  const plotW = CHART_W - MARGIN.left - MARGIN.right;
  if (useLog) {
    const l0 = Math.log10(lo);
    const span = Math.log10(hi) - l0 || 1;
    return {
      useLog: true,
      bins,
      lo,
      hi,
      plotW,
      x: (v) => MARGIN.left + ((Math.log10(clamp(v, lo, hi)) - l0) / span) * plotW,
      density: (slug) => entry.log.cities[slug]?.hist_density || [],
    };
  }
  const span = hi - lo || 1;
  return {
    useLog: false,
    bins,
    lo,
    hi,
    plotW,
    x: (v) => MARGIN.left + ((clamp(v, lo, hi) - lo) / span) * plotW,
    density: (slug) => entry.cities[slug]?.hist_density || [],
  };
}

function clamp(v, lo, hi) {
  return Math.min(hi, Math.max(lo, v));
}

// ---- histogram ------------------------------------------------------------

function renderHistogram(entry, cityIds) {
  const ctx = scaleContext(entry, cityIds);
  const plotH = CHART_H - MARGIN.top - MARGIN.bottom;
  const baseY = MARGIN.top + plotH;

  let maxDensity = 0;
  for (const slug of cityIds) {
    for (const d of ctx.density(slug)) maxDensity = Math.max(maxDensity, d);
  }
  const y = (d) => baseY - (maxDensity ? (d / maxDensity) * plotH : 0);

  const layers = cityIds
    .map((slug) => {
      const c = entry.cities[slug];
      const color = cityColor(slug);
      const density = ctx.density(slug);
      const bars = density
        .map((d, i) => {
          const x0 = ctx.x(ctx.bins[i]);
          const x1 = ctx.x(ctx.bins[i + 1]);
          const yTop = y(d);
          return `<rect x="${x0.toFixed(1)}" y="${yTop.toFixed(1)}" width="${Math.max(0, x1 - x0).toFixed(1)}" height="${(baseY - yTop).toFixed(1)}" fill="${color}" fill-opacity="0.32" stroke="${color}" stroke-opacity="0.7" stroke-width="0.5" />`;
        })
        .join("");
      const band = c.scale_undefined
        ? ""
        : `<rect x="${Math.min(ctx.x(c.band_low), ctx.x(c.band_high)).toFixed(1)}" y="${MARGIN.top}" width="${Math.abs(ctx.x(c.band_high) - ctx.x(c.band_low)).toFixed(1)}" height="${plotH}" fill="${color}" fill-opacity="0.08" />`;
      const medianX = ctx.x(c.median).toFixed(1);
      const medianLine = `<line x1="${medianX}" x2="${medianX}" y1="${MARGIN.top}" y2="${baseY}" stroke="${color}" stroke-width="1.5" stroke-dasharray="3 2" />`;
      return `${band}${bars}${medianLine}`;
    })
    .join("");

  const axis = `<line x1="${MARGIN.left}" x2="${MARGIN.left + ctx.plotW}" y1="${baseY}" y2="${baseY}" class="analytics-axis" />`;
  const ticks = renderXTicks(ctx, baseY);
  const yLabel = `<text x="${MARGIN.left}" y="${MARGIN.top - 4}" class="analytics-axis-title" text-anchor="start">densidad</text>`;
  const unitLabel = renderXUnit(entry, ctx, baseY);
  const overflow = ctx.useLog ? "" : renderOverflowLabels(entry, cityIds, ctx);

  return `
    <svg class="analytics-histogram" viewBox="0 0 ${CHART_W} ${CHART_H}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Histograma de densidad por ciudad, con mediana y banda robusta doble-MAD${ctx.useLog ? ", eje X en escala logaritmica" : ""}">
      ${axis}${layers}${overflow}${ticks}${yLabel}${unitLabel}
    </svg>
  `;
}

function renderOverflowLabels(entry, cityIds, ctx) {
  const marks = [];
  cityIds.forEach((slug, i) => {
    const c = entry.cities[slug];
    const color = cityColor(slug);
    const yPos = MARGIN.top + 10 + i * 10;
    if (c.overflow_low > 0) {
      marks.push(
        `<text x="${MARGIN.left + 2}" y="${yPos}" class="analytics-overflow-label" fill="${color}">&#8676;${c.overflow_low}</text>`,
      );
    }
    if (c.overflow_high > 0) {
      marks.push(
        `<text x="${(MARGIN.left + ctx.plotW - 2).toFixed(1)}" y="${yPos}" text-anchor="end" class="analytics-overflow-label" fill="${color}">${c.overflow_high}&#8677;</text>`,
      );
    }
  });
  return marks.join("");
}

// ---- eCDF -----------------------------------------------------------------

function renderEcdf(entry, cityIds) {
  const ctx = scaleContext(entry, cityIds);
  const plotH = CHART_H - MARGIN.top - MARGIN.bottom;
  const baseY = MARGIN.top + plotH;
  const y = (p) => MARGIN.top + plotH - p * plotH;

  const lines = cityIds
    .map((slug) => {
      const c = entry.cities[slug];
      const xs = c.ecdf?.x || [];
      const ys = c.ecdf?.y || [];
      if (!xs.length) return "";
      const color = cityColor(slug);
      const path = xs
        .map((v, i) => `${i === 0 ? "M" : "L"}${ctx.x(v).toFixed(1)},${y(ys[i]).toFixed(1)}`)
        .join(" ");
      return `<path d="${path}" fill="none" stroke="${color}" stroke-width="1.8" />`;
    })
    .join("");

  const marker = renderKsMarker(entry, cityIds, ctx, y);
  const axis = `<line x1="${MARGIN.left}" x2="${MARGIN.left + ctx.plotW}" y1="${baseY}" y2="${baseY}" class="analytics-axis" />`;
  const yAxis = `<line x1="${MARGIN.left}" x2="${MARGIN.left}" y1="${MARGIN.top}" y2="${baseY}" class="analytics-axis" />`;
  const yTicks = [0, 0.5, 1]
    .map(
      (p) =>
        `<text x="${MARGIN.left - 5}" y="${(y(p) + 3).toFixed(1)}" class="analytics-tick" text-anchor="end">${p}</text>` +
        `<line x1="${MARGIN.left - 3}" x2="${MARGIN.left}" y1="${y(p).toFixed(1)}" y2="${y(p).toFixed(1)}" class="analytics-axis" />`,
    )
    .join("");
  const ticks = renderXTicks(ctx, baseY);
  const yLabel = `<text x="${MARGIN.left}" y="${MARGIN.top - 4}" class="analytics-axis-title" text-anchor="start">F(x)</text>`;
  const unitLabel = renderXUnit(entry, ctx, baseY);

  return `
    <svg class="analytics-ecdf" viewBox="0 0 ${CHART_W} ${CHART_H}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Curva acumulada empirica por ciudad, con brecha maxima de Kolmogorov-Smirnov marcada">
      ${axis}${yAxis}${yTicks}${lines}${marker}${ticks}${yLabel}${unitLabel}
    </svg>
  `;
}

// Only drawn for exactly 2 selected cities: with more, the pairwise KS gaps
// multiply and a single marker would misleadingly suggest one "the" gap.
function renderKsMarker(entry, cityIds, ctx, y) {
  if (cityIds.length !== 2) return "";
  const gap = maxEcdfGap(entry, cityIds[0], cityIds[1]);
  if (!gap) return "";
  const gx = ctx.x(gap.x).toFixed(1);
  return `<line x1="${gx}" x2="${gx}" y1="${y(0).toFixed(1)}" y2="${y(1).toFixed(1)}" class="analytics-ks-marker" stroke-dasharray="2 2" />`;
}

function stepEval(xs, ys, atX) {
  let value = 0;
  for (let i = 0; i < xs.length && xs[i] <= atX; i++) value = ys[i];
  return value;
}

function maxEcdfGap(entry, aSlug, bSlug) {
  const a = entry.cities[aSlug]?.ecdf;
  const b = entry.cities[bSlug]?.ecdf;
  if (!a?.x?.length || !b?.x?.length) return null;
  const allX = [...a.x, ...b.x].sort((p, q) => p - q);
  let best = { x: allX[0], gap: -1 };
  for (const v of allX) {
    const gap = Math.abs(stepEval(a.x, a.y, v) - stepEval(b.x, b.y, v));
    if (gap > best.gap) best = { x: v, gap };
  }
  return best;
}

function renderXTicks(ctx, yPos) {
  const values = ctx.useLog
    ? [ctx.lo, Math.sqrt(ctx.lo * ctx.hi), ctx.hi]
    : [ctx.lo, (ctx.lo + ctx.hi) / 2, ctx.hi];
  return values
    .map(
      (v) =>
        `<text x="${ctx.x(v).toFixed(1)}" y="${(yPos + 13).toFixed(1)}" class="analytics-tick" text-anchor="middle">${fmtEs(v)}</text>`,
    )
    .join("");
}

function renderXUnit(entry, ctx, baseY) {
  const unit = entry.unit || "sin unidad";
  const suffix = ctx.useLog ? ` · log₁₀` : "";
  return `<text x="${(MARGIN.left + ctx.plotW).toFixed(1)}" y="${(baseY + 26).toFixed(1)}" class="analytics-axis-unit" text-anchor="end">${escHtml(unit)}${suffix}</text>`;
}

// ---- LECTURA (prose verdict) ----------------------------------------------

function renderReadout(entry, cityIds) {
  const noun = entry.sample_level === "fine" ? "pixeles" : "unidades";
  const unit = entry.unit ? ` ${entry.unit}` : "";
  const perCity = cityIds
    .map((slug) => {
      const c = entry.cities[slug];
      const missing = c.n_dropped_nan ? ` (${c.n_dropped_nan} sin dato)` : "";
      const spread = c.scale_undefined
        ? "dispersión no definida (columna casi constante)"
        : `dispersión robusta −${fmtEs(c.sigma_lower)}/+${fmtEs(c.sigma_upper)}`;
      return `<p class="analytics-line">
        <span class="analytics-line-city" style="color:${cityColor(slug)}">${escHtml(cityName(slug))}</span>:
        ${fmtInt(c.n)} ${noun}${missing}; la mitad está bajo <strong>${fmtEs(c.median)}${escHtml(unit)}</strong> (mediana); ${spread}.
      </p>`;
    })
    .join("");

  const verdict = renderVerdict(entry, cityIds);
  const warning = entry.warnings?.includes("spatial_autocorrelation")
    ? `<p class="analytics-warning">&#9888; Con miles de pixeles espacialmente autocorrelacionados el p-value colapsa a ~0 aunque la diferencia real sea pequena. Lee primero el tamano de efecto (D, A&sup2;), no el p-value.</p>`
    : "";

  return `
    <div class="analytics-readout" role="region" aria-label="Lectura estadistica">
      <div class="analytics-readout-head">LECTURA</div>
      ${perCity}
      ${verdict}
      ${warning}
      <span class="analytics-cursor" aria-hidden="true">&#9646;</span>
    </div>
  `;
}

function renderVerdict(entry, cityIds) {
  if (cityIds.length < 2) {
    return '<p class="analytics-line analytics-line-muted">Selecciona 2 o mas ciudades para comparar sus distribuciones.</p>';
  }
  const ksAll = entry.tests?.ks || [];
  const ks = ksAll.filter((p) => cityIds.includes(p.a) && cityIds.includes(p.b));
  const ksHtml = ks
    .map((p) => {
      const pct = Math.round(p.d * 100);
      const gauge = renderDGauge(p.d, cityColor(p.a), cityColor(p.b));
      return `<p class="analytics-line">
        En su punto de mayor separación, las curvas acumuladas de
        <strong>${escHtml(cityName(p.a))}</strong> y <strong>${escHtml(cityName(p.b))}</strong>
        difieren en <strong>${pct} puntos porcentuales</strong>
        <span class="analytics-line-muted">(Kolmogorov–Smirnov D=${fmtEs(p.d)}; 0 = idénticas, 1 = sin superposición; p=${fmtP(p.p)})</span>.
      </p>${gauge}`;
    })
    .join("");

  const ad = entry.tests?.ad;
  let adHtml = "";
  if (ad && ad.cities.length === cityIds.length && ad.cities.every((c) => cityIds.includes(c))) {
    // scipy clips p at both ends of its table and they mean OPPOSITE things:
    // floor (p<=0.001) = clearly different; ceiling (p>=0.25) = indistinguishable.
    let tail;
    if (ad.p_cap_side === "floor") {
      tail = `cae bajo el mínimo de la tabla del test (p&le;${fmtP(ad.p)}): señal fuerte de distribuciones distintas`;
    } else if (ad.p_cap_side === "ceiling") {
      tail = `llega al techo de la tabla del test (p&ge;${fmtP(ad.p)}): no se distinguen con este test`;
    } else {
      tail = `p=${fmtP(ad.p)}`;
    }
    adHtml = `<p class="analytics-line">
      Anderson–Darling, que pondera más las colas, entrega <strong>A²=${fmtEs(ad.a2)}</strong> — ${tail}.
    </p>`;
  }

  return ksHtml + adHtml;
}

function renderDGauge(d, colorA, colorB) {
  const pct = Math.max(0, Math.min(1, d)) * 100;
  return `
    <div class="analytics-gauge" role="img" aria-label="Tamano de efecto D = ${fmtEs(d)} en escala 0 a 1">
      <span class="analytics-gauge-end" style="color:${colorA}">0</span>
      <span class="analytics-gauge-track">
        <span class="analytics-gauge-fill" style="width:${pct.toFixed(1)}%"></span>
        <span class="analytics-gauge-mark" style="left:${pct.toFixed(1)}%"></span>
      </span>
      <span class="analytics-gauge-end" style="color:${colorB}">1</span>
    </div>
  `;
}

// ---- methodology tab ------------------------------------------------------

function renderMethodology() {
  return `
    <div class="analytics-method">
      <h3>QUE COMPARA</h3>
      <p>Cada indicador se compara entre las ciudades publicadas mediante dos vistas de su
      <em>distribución</em> completa: un histograma de densidad superpuesto y la curva
      acumulada empírica (eCDF). Se muestra <strong>todo</strong> el dato dentro del área de
      estudio de cada ciudad — nada se recorta para "limpiar" la comparación.</p>

      <h3>DOS MUESTRAS: FINA Y ADMIN</h3>
      <p><span class="analytics-badge analytics-badge-fine">FINA</span> es el valor por píxel del
      producto nativo (miles de puntos por ciudad; hoy PM2.5, NO₂, ALAN, viento y verde).
      <span class="analytics-badge analytics-badge-admin">ADMIN</span> es un valor por comuna/unidad
      administrativa (decenas de puntos). Nunca se mezclan los dos niveles de un mismo físico: el
      NO₂ fino es columna troposférica (mol/m²) y el admin es un proxy de superficie (µg/m³), dos
      cantidades distintas.</p>

      <h3>MEDIANA Y BANDA DOBLE-MAD</h3>
      <p>La línea punteada marca la <strong>mediana</strong>. La banda sombreada es
      mediana ± 3·σ̂, con σ̂ derivado de la desviación absoluta mediana (MAD) calculada por separado
      bajo y sobre la mediana (doble-MAD asimétrico), porque casi todos los exposomas son sesgados a
      la derecha. La estadística robusta resiste los valores extremos sin borrarlos.</p>

      <h3>DESBORDE, NO RECORTE</h3>
      <p>El eje X del histograma usa un rango robusto; los valores fuera de ese rango no se descartan,
      se cuentan y se anotan en los bordes (⇤N / N⇥). Así un puñado de valores extremos no aplasta la
      escala visual de la masa central. La escala log (cuando todos los valores son &gt; 0) comprime la
      cola derecha sin necesidad de desborde.</p>

      <h3>KS Y ANDERSON–DARLING</h3>
      <p><strong>Kolmogorov–Smirnov</strong> mide D = la brecha máxima entre dos curvas acumuladas,
      acotada en 0–1 (0 = idénticas, 1 = sin superposición). <strong>Anderson–Darling k-muestral</strong>
      pondera más las colas y compara todas las ciudades a la vez. Ambos se calculan en Python con scipy;
      el webapp solo dibuja el resultado.</p>

      <h3>EL PROBLEMA DEL n GRANDE</h3>
      <p>Dos ciudades distintas son, <em>a priori</em>, distintas: "misma distribución" es una hipótesis
      de paja. Con miles de píxeles espacialmente autocorrelacionados el p-value colapsa a ~0 sin importar
      cuán chica sea la diferencia real. Por eso el panel antepone siempre el <strong>tamaño de efecto</strong>
      (D, A²) y trata el p-value como secundario, con una advertencia explícita en las muestras finas.</p>
    </div>
  `;
}

// ---- formatting -----------------------------------------------------------

function fmtEs(value, digits = 2) {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  let d = digits;
  if (abs >= 100) d = 0;
  else if (abs >= 10) d = 1;
  return value.toLocaleString("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: d });
}

function fmtInt(value) {
  if (!Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("es-CL");
}

function fmtP(value) {
  if (!Number.isFinite(value)) return "—";
  if (value <= 0) return "0";
  if (value < 0.001) return value.toExponential(1).replace(".", ",");
  return value.toLocaleString("es-CL", { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
