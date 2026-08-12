// CITY_OVERVIEW panel: shows exposomes grouped by category.
// Rendered as an overlay on top of the LATAM map.
//
// State: LATAM -> CITY -> COMMUNE
// - LATAM: world map with city markers
// - CITY: overlay panel with exposome categories (Entorno / Sociedad)
// - COMMUNE: zoomed city map + air chamber + profile

import { getPalette } from "../palette.js";
import { getStudyManifest } from "../data-repository.js";
import { spatialUnitLabel } from "../utils/spatial-unit.js";

let _panel = null;
let _onSelectExposome = null;
let _onBack = null;
let _onOpenLocationProfile = null;
let _mode = "city";
let _currentGroupId = null;
let _context = {
  cityName: "Ciudad",
  cityStats: {},
  backLabel: "\u2190 MUNDO",
};

const CATEGORY_LABELS = {
  entorno: {
    title: "Naturales",
    subtitle: "Exposoma físico-ambiental",
  },
  sociedad: {
    title: "Sociales",
    subtitle: "Contexto socioeconómico y redes",
  },
  resultados: {
    title: "Resultados y asociaciones",
    subtitle: "Mapas ecológicos separados del exposoma",
  },
};

export function initCityOverviewPanel(onSelectExposome, onBack, onOpenLocationProfile = null) {
  _onSelectExposome = onSelectExposome;
  _onBack = onBack;
  _onOpenLocationProfile = onOpenLocationProfile;
  _panel = document.getElementById("cityOverviewPanel");
  if (!_panel) {
    console.warn("initCityOverviewPanel: #cityOverviewPanel not found");
    return;
  }
  _currentGroupId = null;
  _panel.innerHTML = renderPanel();
  attachListeners();
}

export function showCityOverview(cityName, cityStats, options = {}) {
  if (!_panel) return;
  _mode = options.mode || "city";
  _context = {
    cityName: cityName || "Ciudad",
    cityStats: cityStats || {},
    backLabel: options.backLabel || "\u2190 MUNDO",
  };
  const content = _panel.querySelector("#cityPanelContent");
  if (content) content.innerHTML = renderMainContent();
  updateHeader();
  attachContentListeners();
  _panel.hidden = false;
  _panel.dataset.mode = _mode;
  _panel.classList.add("visible");
}

export function hideCityOverview() {
  if (!_panel) return;
  _panel.classList.remove("visible");
  _panel.hidden = true;
}

export function isCityOverviewVisible() {
  return _panel ? _panel.classList.contains("visible") && !_panel.hidden : false;
}

function renderPanel() {
  return `
    <div class="city-panel-header">
      <button class="city-panel-back" id="cityPanelBack" type="button">&larr; MUNDO</button>
      <h2 class="city-panel-name" id="cityPanelName">Ciudad</h2>
      <p class="city-panel-stats" id="cityPanelStats"></p>
    </div>
    <div class="city-panel-content" id="cityPanelContent">
      ${renderMainContent()}
    </div>
  `;
}

function renderMainContent() {
  const palette = getPalette();
  const exposomes = palette?.exposomes || {};
  // Group by category, preserving palette order.
  const groups = { entorno: [], sociedad: [], resultados: [] };
  for (const [id, e] of Object.entries(exposomes)) {
    if (e.parent) continue;
    const cat = e.category || "entorno";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(withChildren({ id, ...e }, exposomes));
  }
  return `
    ${renderLocationProfileAction()}
    <div class="city-categories">
      ${renderCategory("entorno", groups.entorno)}
      ${renderCategory("sociedad", groups.sociedad)}
      ${renderCategory("resultados", groups.resultados)}
    </div>
  `;
}

function renderLocationProfileAction() {
  if (!_onOpenLocationProfile) return "";
  if (_context.cityStats?.mode === "native") {
    return `
      <div class="city-local-profile-action">
        <div>
          <span class="city-local-profile-title">Modo nativo</span>
          <span class="city-local-profile-copy">Esta ciudad conserva la resolución original de sus fuentes.</span>
        </div>
      </div>
    `;
  }
  return `
    <div class="city-local-profile-action">
      <div>
        <span class="city-local-profile-title">Perfil local</span>
        <span class="city-local-profile-copy">Radar relativo por ZIP o punto manual en ${escHtml(_context.cityName || "la ciudad")}.</span>
      </div>
      <button class="city-local-profile-button" id="cityLocalProfileButton" type="button">
        Abrir radar
      </button>
    </div>
  `;
}

function updateHeader() {
  if (!_panel) return;
  const nameEl = _panel.querySelector("#cityPanelName");
  const statsEl = _panel.querySelector("#cityPanelStats");
  const backBtn = _panel.querySelector("#cityPanelBack");
  if (nameEl) nameEl.textContent = _context.cityName || "Ciudad";
  if (backBtn) backBtn.textContent = _context.backLabel || "\u2190 MUNDO";
  if (!statsEl) return;
  const stats = _context.cityStats || {};
  const unitWord = spatialUnitLabel(
    getStudyManifest()?.spatial?.unit_type,
    { plural: true },
  );
  const parts = [];
  if (stats.n_communes) parts.push(`${stats.n_communes} ${unitWord}`);
  if (stats.n_indicators) parts.push(`${stats.n_indicators} indicadores`);
  if (stats.n_layers) parts.push(`${stats.n_layers} capas`);
  statsEl.textContent = parts.length ? parts.join(" \u00b7 ") : "";
}

function withChildren(exposome, allExposomes) {
  const children = resolveChildren(exposome.id, allExposomes);
  return children.length ? { ...exposome, children } : exposome;
}

function resolveChildren(groupId, allExposomes) {
  const group = allExposomes[groupId] || {};
  const explicit = Array.isArray(group.children) ? group.children : [];
  const ids = explicit.length
    ? explicit
    : Object.entries(allExposomes)
        .filter(([, e]) => e.parent === groupId)
        .map(([id]) => id);
  return ids
    .map((id) => (allExposomes[id] ? { id, ...allExposomes[id] } : null))
    .filter(Boolean);
}

function renderCategory(catKey, exposomes) {
  const label = CATEGORY_LABELS[catKey] || { title: catKey, subtitle: "" };
  const count = exposomes.length;
  return `
    <div class="city-category" data-category="${catKey}">
      <h3>${escHtml(label.title)} (${count})</h3>
      <p class="city-category-subtitle">${escHtml(label.subtitle)}</p>
      <div class="city-cards">
        ${exposomes.length === 0
          ? '<p class="city-category-empty">Próximamente</p>'
          : exposomes.map(renderCard).join("")}
      </div>
    </div>
  `;
}

function renderCard(e) {
  const isGroup = Array.isArray(e.children) && e.children.length > 0;
  const ready = e.status === "ready" && (isGroup
    ? e.children.some((child) => isLayerAvailable(child.id))
    : isLayerAvailable(e.id));
  const selectable = ready || (isGroup && e.children.some((child) => isLayerAvailable(child.id)));
  const desc = e.description || e.long_description || "";
  const iconId = e.icon_key || e.parent || e.id;
  const explicitAvailability = indicatorAvailability(e.id);
  const badgeClass = selectable && isGroup
    ? "badge-group"
    : ready
      ? "badge-ready"
      : explicitAvailability
        ? "badge-unavailable"
        : "badge-coming-soon";
  const availableChildren = isGroup
    ? e.children.filter((child) => isLayerAvailable(child.id)).length
    : 0;
  const badgeText = isGroup && selectable
    ? `${availableChildren}/${e.children.length} capas`
    // Badge renders in Press Start 2P (uppercase): sin tilde a prop\u00f3sito.
    : ready ? "\u2713 Listo" : availabilityBadge(explicitAvailability);
  const badgeTitle = availabilityTitle(explicitAvailability);
  return `
    <div
      class="exposome-card ${selectable ? "" : "disabled"} ${isGroup ? "is-group" : ""}"
      data-id="${escHtml(e.id)}"
      data-card-type="${isGroup ? "group" : "exposome"}"
    >
      <div class="exposome-card-icon icon-${escHtml(iconId)}"></div>
      <div class="exposome-card-name">${escHtml(e.label)}</div>
      <div class="exposome-card-unit">${escHtml(e.unit || "")}</div>
      <div class="exposome-card-desc">${escHtml(desc)}</div>
      <div class="exposome-card-badge ${badgeClass}"${badgeTitle ? ` title="${escHtml(badgeTitle)}"` : ""}>
        ${escHtml(badgeText)}
      </div>
    </div>
  `;
}

function indicatorAvailability(id) {
  const value = getStudyManifest()?.spatial_indicators?.[id]?.availability;
  return value && typeof value === "object" ? value : null;
}

function availabilityBadge(availability) {
  if (availability?.reason === "country_not_supported") {
    const countries = availability.supported_countries || [];
    return countries.length ? `Solo ${countries.join("/")}` : "Fuera de cobertura";
  }
  if (["not_enabled_by_study", "not_published_by_study"].includes(availability?.reason)) {
    return "No publicado";
  }
  return "\u23f3 Proximamente";
}

function availabilityTitle(availability) {
  if (availability?.reason === "country_not_supported") {
    const countries = availability.supported_countries || [];
    return countries.length
      ? `Fuente disponible solo en ${countries.join(", ")}`
      : "Fuente no disponible para este pais";
  }
  if (availability?.reason === "not_enabled_by_study") {
    return "Capa no habilitada en este estudio";
  }
  if (availability?.reason === "not_published_by_study") {
    return "Capa habilitada pero no publicada";
  }
  if (availability?.reason === "coming_soon") return "Indicador en preparacion";
  return "";
}

function isLayerAvailable(id) {
  const manifest = getStudyManifest();
  const explicitAvailability = indicatorAvailability(id);
  if (explicitAvailability?.status === "available") return true;
  if (explicitAvailability?.status === "unavailable") return false;
  const columns = manifest?.columns;
  const definition = getPalette()?.exposomes?.[id];
  const column = definition?.column;
  if (definition?.data_asset) {
    return Boolean(
      manifest?.assets?.outcomes_catalog && manifest?.layers?.[id]?.available !== false
    );
  }
  if (Array.isArray(columns) && columns.length && column) {
    return columns.includes(column);
  }
  // Legacy bundles / native studies without a columns manifest: fall back
  // to the pipeline layer ids listed in the catalog.
  const available = _context.cityStats?.layers;
  if (!Array.isArray(available) || !available.length) return true;
  const aliases = { pm25: "air_quality_pm25" };
  return available.includes(id) || available.includes(aliases[id]);
}

function renderGroupContent(groupId) {
  const palette = getPalette();
  const exposomes = palette?.exposomes || {};
  const group = exposomes[groupId] ? { id: groupId, ...exposomes[groupId] } : null;
  const children = resolveChildren(groupId, exposomes);
  return `
    <div class="city-subpanel">
      <div class="city-subpanel-header">
        <button class="city-subpanel-back" id="citySubpanelBack" type="button">&larr; Exposomas</button>
        <div>
          <h3>${escHtml(group?.label || groupId)}</h3>
          <p>${escHtml(group?.long_description || group?.description || "")}</p>
        </div>
      </div>
      <div class="city-cards city-subcards">
        ${children.length === 0
          ? '<p class="city-category-empty">Sin subcapas disponibles.</p>'
          : children.map(renderCard).join("")}
      </div>
    </div>
  `;
}

function showMainCategories() {
  if (!_panel) return;
  _currentGroupId = null;
  delete _panel.dataset.group;
  const content = _panel.querySelector("#cityPanelContent");
  if (content) content.innerHTML = renderMainContent();
  attachContentListeners();
}

function showGroup(groupId) {
  if (!_panel) return;
  _currentGroupId = groupId;
  _panel.dataset.group = groupId;
  const content = _panel.querySelector("#cityPanelContent");
  if (content) content.innerHTML = renderGroupContent(groupId);
  attachContentListeners();
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function attachListeners() {
  const backBtn = _panel.querySelector("#cityPanelBack");
  if (backBtn) {
    backBtn.addEventListener("click", () => {
      if (_onBack) _onBack();
    });
  }
  attachContentListeners();
}

function attachContentListeners() {
  _panel.querySelector("#citySubpanelBack")?.addEventListener("click", showMainCategories);
  _panel.querySelector("#cityLocalProfileButton")?.addEventListener("click", () => {
    if (_onOpenLocationProfile) _onOpenLocationProfile();
  });
  _panel.querySelectorAll(".exposome-card").forEach((card) => {
    card.addEventListener("click", () => {
      if (card.classList.contains("disabled")) return;
      const id = card.dataset.id;
      if (!id) return;
      if (card.dataset.cardType === "group") {
        showGroup(id);
        return;
      }
      if (_onSelectExposome) _onSelectExposome(id);
    });
    // Keyboard support: Enter / Space on focused card.
    card.setAttribute("tabindex", "0");
    card.setAttribute("role", "button");
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        card.click();
      }
    });
  });
}
