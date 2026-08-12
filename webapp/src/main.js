// Main orchestrator. Loads palette, sets up the state machine
// (latam <-> commune), wires the creeperLat character, sound,
// tabs, and click handlers.

import { loadPalette, getPalette } from "./palette.js";
import {
  initLatamState,
  flyToCity,
  resetLatamView,
  destroyLatamState,
} from "./states/latam.js";
import {
  initCommuneState,
  flyToCommune,
  getCommuneMap,
  destroyCommuneState,
} from "./states/commune.js";
import { initNativeState, destroyNativeState } from "./states/native.js";
import { setupCharacter, setMood } from "./character/sprite.js";
import { navigateTo } from "./character/navigation.js";
import { setupSound, play, stopAllLoops } from "./sound.js";
import { getMaster } from "./choropleth.js";
import {
  getCityRecord,
  getStudyManifest,
  loadCatalog,
  selectStudy,
  studyAsset,
  assetUrl,
  studyDetailAsset,
  studyHasFineLayer,
  studySpatialIndicator,
  studyAnnualYears,
  studyTemporalIndicator,
  temporalSeriesRequiresSpatialDetail,
  temporalSeriesSpatiallyComplete,
  studyHasColumn,
} from "./data-repository.js";
import {
  destroyLocationProfile,
  initLocationProfile,
  openLocationProfilePicker,
  restoreLocationProfileFromState,
} from "./location-profile.js";
import {
  getInitialState,
  setURLState,
  onPopState,
} from "./utils/url-state.js";
import { spatialSupportText, withMapSupport } from "./utils/spatial-support.js";
import { spatialUnitLabel } from "./utils/spatial-unit.js";

const STATE = { LATAM: "latam", CITY: "city", COMMUNE: "commune", DOWNLOAD: "download" };
let _state = STATE.LATAM;
let _currentCity = null;
let _currentStudyId = null;
let _appState = getInitialState();
let _activeExposome = _appState.exposome || "pm25";
const _profileCache = new Map();
let _cityNavigationGeneration = 0;

async function main() {
  try {
    await loadPalette();
    await loadCatalog();
    _activeExposome = resolveSelectableExposomeId(_activeExposome);
    _appState = { ..._appState, exposome: _activeExposome };
  } catch (err) {
    console.error("Failed to load palette:", err);
    document.body.innerHTML = `<pre style="color:red;padding:24px;">${err.message}</pre>`;
    return;
  }

  setupSound();

  try {
    await initLatamState("app", "map", handleCityClick, openAnalyticsPanel, openPointDownloadPanel);
  } catch (err) {
    console.error("LATAM init failed:", err);
    return;
  }

  setupBackButton();
  setupPopState();
  updateSubtitle();

  renderCommuneExposomeSwitcher();

  // ?view=download opens the point-download tab straight away. It is
  // city-independent, so it is checked before the city-based transitions.
  if (_appState.view === STATE.DOWNLOAD) {
    await openPointDownloadPanel();
    return;
  }

  // Auto-transition to commune if URL says so.
  if (_appState.city && (_appState.view === STATE.COMMUNE || _appState.view === STATE.CITY)) {
    const requestedView = _appState.view;
    const enteredCity = await handleCityClick(_appState.city);
    if (enteredCity && requestedView === STATE.COMMUNE) {
      await transitionToCommune(_activeExposome);
    }
  }
}

function updateSubtitle() {
  const sub = document.getElementById("appSubtitle");
  if (!sub) return;
  if (_state === STATE.LATAM) {
    sub.textContent = "Pixel edition · Mundo";
  } else {
    const cityName = _currentCity
      ? (getCityRecord(_currentCity)?.name || _currentCity)
      : getStudyManifest()?.location?.name || "—";
    sub.textContent = `Pixel edition · ${cityName}`;
  }
}

function setupPopState() {
  onPopState((newState) => {
    _appState = { ..._appState, ...newState };
    if (newState.view === STATE.DOWNLOAD) {
      openPointDownloadPanel();
      return;
    }
    // Leaving ?view=download by going back must close the panel, or it stays
    // on top of whatever view the history entry restores.
    hidePointDownloadPanelIfOpen();
    if (newState.view === STATE.LATAM && (_state === STATE.COMMUNE || _state === STATE.CITY)) {
      transitionToLatam();
    }
  });
}

async function openAnalyticsPanel() {
  const { initAnalyticsPanel, showAnalyticsPanel } = await import("./panels/analytics-compare.js");
  initAnalyticsPanel();
  await showAnalyticsPanel();
}

async function hideAnalyticsPanelIfOpen() {
  try {
    const { hideAnalyticsPanel } = await import("./panels/analytics-compare.js");
    hideAnalyticsPanel();
  } catch (e) { /* module not loaded yet */ }
}

async function openPointDownloadPanel() {
  const { initPointDownloadPanel, showPointDownloadPanel } =
    await import("./panels/point-download.js");
  initPointDownloadPanel(() => setURLState({ view: STATE.LATAM }));
  await showPointDownloadPanel();
  setURLState({ view: STATE.DOWNLOAD });
}

async function hidePointDownloadPanelIfOpen() {
  try {
    const { hidePointDownloadPanel } = await import("./panels/point-download.js");
    hidePointDownloadPanel();
  } catch (e) { /* module not loaded yet */ }
}

async function handleCityClick(slug) {
  const city = getCityRecord(slug);
  if (!city?.available || !city.study_id) return false;
  const generation = ++_cityNavigationGeneration;
  _profileCache.clear();
  return transitionToCity(city, generation);
}

async function transitionToCommune(exposomeId, options = {}) {
  await selectStudy(_currentStudyId || "santiago_communes");
  _activeExposome = resolveSelectableExposomeId(exposomeId || _activeExposome || "pm25");
  _appState = { ..._appState, view: STATE.COMMUNE, city: _currentCity || "santiago", exposome: _activeExposome };
  setURLState(_appState);
  showLoading(true, "Cargando exposome...");
  // Safety net: force-hide the overlay after 10s if anything hangs.
  const safetyTimeout = setTimeout(() => {
    console.warn("transitionToCommune: safety timeout (10s), forcing overlay hide");
    showLoading(false);
  }, 10000);
  try {
    // 0. Hide the CITY panel overlay (if visible).
    try {
      const { hideCityOverview } = await import("./panels/city-overview.js");
      hideCityOverview();
    } catch (e) { /* module not loaded yet */ }
    await hideAnalyticsPanelIfOpen();
    await hidePointDownloadPanelIfOpen();

    // 1. Destroy the LATAM map BEFORE creating the commune map.
    //    This avoids two MapLibre instances on the same DOM node,
    //    which prevented the new map's `load` event from firing.
    destroyLatamState();
    const manifest = getStudyManifest();
    if (manifest?.mode === "native") {
      // Native studies do not invent aggregate polygons. The adapter draws
      // their AOI and any web preview declared by the layer manifest.
      await initNativeState("map", null, _activeExposome);
      _state = STATE.COMMUNE;
      showBackButton(true);
      showCommuneUI(true);
      updateSubtitle();
      renderCommuneExposomeSwitcher();
      return;
    }
    // 2. Initialize the aggregate study map. Its center and bounds come from
    // the selected manifest rather than Santiago constants.
    await initCommuneState("map", handleCommuneClick, _activeExposome);
    // 2b. Update airchamber labels to match this exposome.
    try {
      const { setChamberCopy } = await import("./visualizations/airchamber.js");
      const activeExpo = getPalette().exposomes[_activeExposome];
      const spatialOptions = activeExpo?.default_year
        ? { year: String(activeExpo.default_year) }
        : undefined;
      setChamberCopy(withMapSupport(
        activeExpo,
        studySpatialIndicator(_activeExposome, spatialOptions),
      ));
    } catch (e) { /* airchamber not yet initialized — will be set by initAirchamber */ }
    renderCommuneExposomeSwitcher();
    await updateOutcomePanel();
    // 3. Set up creeperLat.
    await setupCharacter("characterContainer");
    setMood("active");
    // 4. Pre-load a default commune (Lo Espejo, the top-1 EBI).
    //    Wrapped in try/catch: if the profile fetch fails, the
    //    user can still click any commune manually.
    try {
      await loadDefaultCommune();
    } catch (loadErr) {
      console.warn("loadDefaultCommune failed (continuing):", loadErr);
    }
    // 5. Update state + URL.
    _state = STATE.COMMUNE;
    showBackButton(true);
    showCommuneUI(true);
    updateSubtitle();
    await setupLocationProfile(options);
  } catch (err) {
    console.error("transitionToCommune failed at step:", err);
    showLoading(true, `Error: ${err.message}`);
  } finally {
    clearTimeout(safetyTimeout);
    showLoading(false);
  }
}

// Transition to the CITY_OVERVIEW panel: shows the exposome
// categories overlay on top of the LATAM map (which stays visible
// as background context).
async function transitionToCity(city, generation) {
  const isCurrent = () => generation === _cityNavigationGeneration;
  showLoading(true, `Cargando exposomas de ${city.name || "la ciudad"}...`);
  let completed = false;
  try {
    await hideAnalyticsPanelIfOpen();
    await hidePointDownloadPanelIfOpen();
    await selectStudy(city.study_id);
    if (!isCurrent()) return false;
    // Init + show the CITY panel.
    const { initCityOverviewPanel, showCityOverview } = await import(
      "./panels/city-overview.js"
    );
    initCityOverviewPanel(
      (exposomeId) => transitionToCommune(exposomeId),
      () => transitionToLatam(),
      () => transitionToCommune(_activeExposome, { openLocationProfile: true }),
    );
    // Look up city metadata for the header.
    showCityOverview(city.name || city.slug, city);
    // Update state + UI classes.
    _currentCity = city.slug;
    _currentStudyId = city.study_id;
    _state = STATE.CITY;
    _appState = { ..._appState, view: STATE.CITY, city: city.slug, commune: null, exposome: _activeExposome };
    setURLState(_appState);
    document.body.classList.remove("latam-mode", "commune-mode");
    document.body.classList.add("city-mode");
    // The overlay carries its own "← MUNDO" button; showing the header
    // back too puts two identical escape buttons 20px apart.
    showBackButton(false);
    showCommuneUI(false);
    updateSubtitle();
    completed = true;
    return true;
  } catch (err) {
    if (!isCurrent()) return false;
    console.error("transitionToCity failed at step:", err);
    showCityLoadError(city, err);
    return false;
  } finally {
    if (completed && isCurrent()) showLoading(false);
  }
}

function showCityLoadError(city, error) {
  const label = city.name || "la ciudad";
  const detail = error?.message ? ` (${error.message})` : "";
  showLoading(
    true,
    `No se pudieron cargar los datos de ${label}.${detail}`,
    {
      error: true,
      retry: () => { void handleCityClick(city.slug); },
      back: () => {
        _cityNavigationGeneration += 1;
        _currentCity = null;
        _currentStudyId = null;
        _state = STATE.LATAM;
        _appState = {
          ..._appState,
          view: STATE.LATAM,
          city: null,
          commune: null,
          loc: null,
          zip: null,
        };
        setURLState(_appState);
        updateSubtitle();
        void resetLatamView();
        showLoading(false);
      },
    },
  );
}

async function loadDefaultCommune() {
  try {
    // Pick the commune with the highest EBI from the master. Reuse the
    // already-loaded master (fetched once in initCommuneState) instead
    // of re-downloading master.geojson.
    const data = getMaster();
    if (!data || !data.features) return;
    // For v0.5, hardcode the most contrasting commune.
    const feat =
      data.features.find((f) => f.properties.slug === "lo_espejo") ||
      data.features[0];
    if (!feat) return;
    const centroid = (() => {
      const g = feat.geometry;
      const ring =
        g.type === "Polygon" ? g.coordinates[0]
        : g.type === "MultiPolygon" ? g.coordinates[0][0]
        : null;
      if (!ring) return null;
      let sx = 0, sy = 0;
      for (const [x, y] of ring) { sx += x; sy += y; }
      return [sx / ring.length, sy / ring.length];
    })();
    const map = getCommuneMap();
    if (map && centroid) {
      map.flyTo({ center: centroid, zoom: 10, duration: 1500, essential: true });
    }
    if (window.__app?.setCommune) {
      window.__app.setCommune({
        slug: feat.properties.slug,
        name: feat.properties.name,
        centroid,
      });
    }
  } catch (err) {
    console.warn("Failed to load default commune:", err);
  }
}

async function transitionToLatam() {
  _cityNavigationGeneration += 1;
  showLoading(true, "Volviendo al mundo...");
  const safetyTimeout = setTimeout(() => {
    console.warn("transitionToLatam: safety timeout (10s), forcing overlay hide");
    showLoading(false);
  }, 10000);
  try {
    // Stop ambient loops.
    stopAllLoops();
    destroyLocationProfile();
    // Hide the CITY panel overlay (if visible).
    try {
      const { hideCityOverview } = await import("./panels/city-overview.js");
      hideCityOverview();
    } catch (e) { /* module not loaded yet */ }
    // Destroy the commune map BEFORE creating a new LATAM map.
    destroyCommuneState();
    destroyNativeState();
    // Apply the LATAM layout classes BEFORE (re-)creating the globe, so
    // its canvas measures the container at its final size (otherwise it
    // ends up mis-sized/off-center while city-mode/commune-mode layout
    // is still applied).
    showBackButton(false);
    showCommuneUI(false);
    document.body.classList.remove("city-mode");
    // Re-create the LATAM map.
    await initLatamState("app", "map", handleCityClick, openAnalyticsPanel, openPointDownloadPanel);
    await resetLatamView();
    // Update state + URL.
    _state = STATE.LATAM;
    _currentCity = null;
    _appState = { ..._appState, view: STATE.LATAM, city: null, commune: null, loc: null, zip: null };
    setURLState(_appState);
    updateSubtitle();
  } catch (err) {
    console.error("transitionToLatam failed:", err);
    showLoading(true, `Error: ${err.message}`);
  } finally {
    clearTimeout(safetyTimeout);
    showLoading(false);
  }
}

async function setupLocationProfile(options = {}) {
  const map = getCommuneMap();
  if (!map) return;
  await initLocationProfile({
    map,
    getState: () => _appState,
    updateState: (patch) => {
      _appState = { ..._appState, ...patch };
      setURLState(_appState);
    },
  });
  const restored = await restoreLocationProfileFromState(_appState);
  if (!restored && options.openLocationProfile) {
    openLocationProfilePicker();
  }
}

function handleCommuneClick(commune) {
  if (window.__app?.setCommune) {
    window.__app.setCommune(commune);
  }
}

function setupBackButton() {
  const btn = document.getElementById("backButton");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (_state === STATE.COMMUNE || _state === STATE.CITY) {
      transitionToLatam();
    }
  });
}

function showBackButton(show) {
  const btn = document.getElementById("backButton");
  if (btn) {
    btn.classList.toggle("visible", show);
  }
}

function showCommuneUI(show) {
  document.body.classList.toggle("commune-mode", show);
  document.body.classList.toggle("latam-mode", !show);
  if (show) document.body.classList.remove("city-mode");
  // Show/hide the right panel.
  const rightPanel = document.getElementById("rightPanel");
  if (rightPanel) rightPanel.hidden = !show;
  updateTimeSliderVisibility(show);
  if (show) {
    updateSpatialLabels();
    renderCommuneExposomeSwitcher();
    // Reset the 1km pixel indicator so it only reappears after the
    // first hover (avoids flashing a stale value when re-entering
    // commune mode).
    const pi = document.getElementById("pixelIndicator");
    if (pi) pi.hidden = true;
    const piVal = document.getElementById("pixelIndicatorValue");
    if (piVal) piVal.textContent = "—";
  }
}

function updateSpatialLabels() {
  const nativeStudy = getStudyManifest()?.mode === "native";
  const summary = document.querySelector("#communeProfileSummary .right-panel-empty");
  if (summary) {
    summary.textContent = nativeStudy
      ? "Selecciona una capa para ver su preview nativo."
      : "Haz click en una unidad espacial para ver su perfil.";
  }
  const panelTitle = document.querySelector("#rightPanel .right-panel-header h2");
  if (panelTitle) panelTitle.textContent = nativeStudy ? "Estudio nativo" : "Perfil";
}

function updateTimeSliderVisibility(show = _state === STATE.COMMUNE) {
  const timeBar = document.getElementById("timeSliderBar");
  const yearBar = document.getElementById("yearTabsBar");
  let expo = null;
  try {
    expo = getPalette().exposomes[_activeExposome];
  } catch (_) {}
  // has_annual/year_columns are global per-exposome declarations (the
  // source has yearly vintages); the slider only shows for the ACTIVE
  // study's bundle if it actually published those years (a study can
  // exist without its annual files or a year_columns column yet — e.g. a
  // just-onboarded city ahead of a full republish).
  const temporal = studyTemporalIndicator(_activeExposome);
  const requiredTemporalIncomplete =
    temporalSeriesRequiresSpatialDetail(_activeExposome)
    && !temporalSeriesSpatiallyComplete(_activeExposome);
  const hasAnnual = studyAnnualYears(_activeExposome).length > 0
    && (!!expo?.has_annual || !!temporal);
  const publishedYearKeys = !requiredTemporalIncomplete && expo?.year_columns
    ? Object.keys(expo.year_columns).filter((y) => studyHasColumn(expo.year_columns[y]))
    : [];
  const nYears = publishedYearKeys.length;
  const nativeStudy = getStudyManifest()?.mode === "native";
  // Few vintages (<=4) read better as segmented tabs (food_insecurity);
  // longer series (heat/rain 2015-2024) reuse the time slider in column
  // mode. `has_annual` keeps the legacy per-year-file slider (pm25).
  const useSlider = !nativeStudy && (hasAnnual || nYears > 4);
  const useTabs = !nativeStudy && !hasAnnual && nYears > 0 && nYears <= 4;
  if (timeBar) {
    const visible = !!show && useSlider;
    timeBar.hidden = !visible;
    if (visible) renderTimeSlider(expo);
    else resetTimeSliderState();
  }
  if (yearBar) {
    const visible = !!show && useTabs;
    yearBar.hidden = !visible;
    if (visible) renderYearTabs(expo);
  }
}

// Active stops of the time slider. Two modes:
//   "files"   — pm25: each year swaps the whole GeoJSON (annual files).
//   "columns" — heat/rain: each year swaps the choropleth column
//               (`year_columns` in palette.json; all columns ship in
//               master.geojson, no extra fetches).
let _sliderStops = [];
let _sliderMode = null;
let _sliderPlaying = false;
let _sliderInterval = null;

function buildSliderStops(expo) {
  const temporal = studyTemporalIndicator(_activeExposome);
  const publishedTemporalYears = studyAnnualYears(_activeExposome);
  if (temporal?.years && publishedTemporalYears.length) {
    const years = publishedTemporalYears;
    const stops = years.map((year) => {
      const harvest = temporal.years[year] || {};
      const sourceLabel = harvest.detail?.temporal_support?.source_label || harvest.source;
      return {
        key: year,
        label: year,
        current: sourceLabel ? `${sourceLabel} ${year}` : year,
        column: temporal.value_column,
        dataAsset: harvest.asset?.path,
        unit: temporal.unit,
        temporalLabel: temporal.label,
        sourceLabel,
      };
    });
    stops.push({
      key: "avg",
      label: "Base",
      current: expo.period_avg || expo.period || "Resumen publicado",
    });
    return { mode: "manifest", stops, defaultIdx: stops.length - 1 };
  }
  if (expo?.has_annual) {
    const years = studyAnnualYears(_activeExposome).map(Number).sort((a, b) => a - b);
    const rangeLabel = years.length ? `${years[0]}-${years[years.length - 1]}` : "";
    return {
      mode: "files",
      stops: [
        ...years.map((y) => ({ key: String(y), label: String(y), current: String(y) })),
        { key: "avg", label: "Prom.", current: `Promedio ${rangeLabel}`.trim() },
      ],
      defaultIdx: years.length,
    };
  }
  const yearKeys = (
    temporalSeriesRequiresSpatialDetail(_activeExposome)
    && !temporalSeriesSpatiallyComplete(_activeExposome)
  ) ? [] : Object.keys(expo?.year_columns || {})
    .filter((y) => studyHasColumn(expo.year_columns[y]))
    .sort();
  const stops = yearKeys.map((y) => ({
    key: y,
    label: y,
    current: (() => {
      const detail = studyDetailAsset(_activeExposome, { year: y });
      const detailSource = detail?.temporal_support?.source_label;
      const source = detailSource || expo.period;
      return source ? `${source} ${y}` : String(y);
    })(),
    column: expo.year_columns[y],
  }));
  // An extra "Prom." stop only when the exposome's base column is a
  // multi-year aggregate distinct from every vintage (rain). When the base
  // column IS one of the vintages (heat: column == year_columns["2024"])
  // there is no honest aggregate to show.
  const hasAggregate = !Object.values(expo.year_columns).includes(expo.column);
  if (hasAggregate) {
    stops.push({
      key: "avg",
      label: "Prom.",
      current: `Promedio ${expo.period_avg || expo.period || ""}`.trim(),
    });
  }
  let defaultIdx = stops.length - 1;
  if (expo.default_year && yearKeys.includes(expo.default_year)) {
    defaultIdx = yearKeys.indexOf(expo.default_year);
  }
  return { mode: "columns", stops, defaultIdx };
}

function renderTimeSlider(expo) {
  const slider = document.getElementById("timeSlider");
  const label = document.getElementById("timeSliderLabel");
  const labelsEl = document.getElementById("timeSliderLabels");
  if (!slider || !label || !labelsEl) return;
  stopSliderPlayback();
  const { mode, stops, defaultIdx } = buildSliderStops(expo);
  _sliderMode = mode;
  _sliderStops = stops;
  slider.max = String(stops.length - 1);
  slider.value = String(defaultIdx);
  labelsEl.innerHTML = stops
    .map(
      (s, i) =>
        `<span data-idx="${i}" data-active="${i === defaultIdx ? "true" : "false"}">${escHtml(s.label)}</span>`,
    )
    .join("");
  labelsEl.querySelectorAll("span").forEach((s) => {
    s.addEventListener("click", () => {
      slider.value = s.dataset.idx;
      applySliderStop(parseInt(s.dataset.idx));
    });
  });
  label.textContent = stops[defaultIdx].current;
  label.classList.remove("no-data");
  // The default paint is dispatched by the caller (addChoropleth resolves
  // `default_year` itself) — here we only sync the vintage state so panel
  // reads target the right column.
  if (mode === "columns") {
    const def = stops[defaultIdx];
    _currentYearTab = def.column ? def.key : null;
  }
  if (mode === "manifest") _currentTemporalColumn = null;
  wireTimeSlider();
}

function wireTimeSlider() {
  const slider = document.getElementById("timeSlider");
  const playBtn = document.getElementById("timeSliderPlay");
  if (!slider || slider.dataset.wired === "1") return;
  slider.dataset.wired = "1";
  slider.addEventListener("input", () => applySliderStop(parseInt(slider.value)));
  playBtn?.addEventListener("click", toggleSliderPlayback);
}

function applySliderStop(idx) {
  const stop = _sliderStops[idx];
  if (!stop) return;
  const label = document.getElementById("timeSliderLabel");
  const labelsEl = document.getElementById("timeSliderLabels");
  if (label) {
    label.textContent = stop.current;
    label.classList.remove("no-data");
  }
  labelsEl?.querySelectorAll("span").forEach((s) => {
    s.dataset.active = s.dataset.idx === String(idx) ? "true" : "false";
  });

  if (_sliderMode === "manifest") {
    const year = stop.key === "avg" ? "avg" : parseInt(stop.key);
    _currentYear = year;
    _currentTemporalColumn = stop.column || null;
    const overrides = stop.dataAsset
      ? {
          column: stop.column,
          data_asset: stop.dataAsset,
          yearLabel: String(stop.key),
          unit: stop.unit,
          label: stop.temporalLabel,
          sourceLabel: stop.sourceLabel,
        }
      : {};
    import("./choropleth.js").then(async (m) => {
      await m.addChoropleth(_activeExposome, overrides);
      const column = stop.column || getPalette().exposomes[_activeExposome]?.column;
      if (column) await refreshPanelValue(column);
    });
    const profileTarget = document.getElementById("communeProfileBody");
    if (profileTarget?.dataset.communeSlug) {
      const profile = window.__app?.getProfileBySlug?.(profileTarget.dataset.communeSlug);
      const series = profile?.timeseries?.[_activeExposome] || [];
      const oldChart = profileTarget.querySelector(".mini-chart");
      if (oldChart && series.length) oldChart.outerHTML = renderMiniChart(series, year);
    }
  } else if (_sliderMode === "files") {
    const year = stop.key === "avg" ? "avg" : parseInt(stop.key);
    _currentYear = year;
    import("./choropleth.js").then((m) => m.setYear(year));
    // Re-render profile mini-chart if a commune is selected.
    const profileTarget = document.getElementById("communeProfileBody");
    if (profileTarget && profileTarget.dataset.communeSlug) {
      const slug = profileTarget.dataset.communeSlug;
      const profile = window.__app?.getProfileBySlug?.(slug);
      if (profile) {
        const ts = profile.timeseries?.[_activeExposome] || [];
        if (ts.length > 0) {
          const newMiniChart = renderMiniChart(ts, year);
          const oldChart = profileTarget.querySelector(".mini-chart");
          if (oldChart) oldChart.outerHTML = newMiniChart;
        }
      }
    }
  } else {
    setYearColumn(stop.column ? stop.key : null);
  }
}

function stopSliderPlayback() {
  if (_sliderInterval) clearInterval(_sliderInterval);
  _sliderInterval = null;
  _sliderPlaying = false;
  const playBtn = document.getElementById("timeSliderPlay");
  if (playBtn) {
    playBtn.textContent = "▶ Play";
    playBtn.classList.remove("playing");
  }
}

function toggleSliderPlayback() {
  const slider = document.getElementById("timeSlider");
  const playBtn = document.getElementById("timeSliderPlay");
  if (!slider || !playBtn) return;
  if (_sliderPlaying) {
    stopSliderPlayback();
    return;
  }
  playBtn.textContent = "⏸ Pause";
  playBtn.classList.add("playing");
  _sliderPlaying = true;
  slider.value = "0";
  applySliderStop(0);
  _sliderInterval = setInterval(() => {
    const idx = (parseInt(slider.value) + 1) % _sliderStops.length;
    slider.value = String(idx);
    applySliderStop(idx);
  }, 800);
}

// Restore neutral state when the slider hides or the exposome changes:
// stop playback and, in file mode, repaint the multi-year average data.
function resetTimeSliderState() {
  stopSliderPlayback();
  if (_sliderMode === "files" && _currentYear !== "avg") {
    _currentYear = "avg";
    import("./choropleth.js").then((m) => m.setYear("avg"));
  }
  _sliderMode = null;
  _sliderStops = [];
  _currentTemporalColumn = null;
}

// Global year state (shared with choropleth.js via setYear).
let _currentYear = "avg";

// Active vintage for exposomes with discrete `year_columns` (e.g.
// food_insecurity CASEN 2020/2022). Reset on every exposome switch.
let _currentYearTab = null;
let _currentTemporalColumn = null;

// Column that should feed the panel/monitor for the active exposome,
// honoring the selected year tab when the exposome has `year_columns`.
function activeExposomeColumn(expo) {
  if (!expo) return null;
  if (_currentTemporalColumn) return _currentTemporalColumn;
  const byYear = expo.year_columns?.[_currentYearTab];
  return byYear || expo.column;
}

function renderYearTabs(expo) {
  const tabs = document.getElementById("yearTabs");
  if (!tabs || !expo?.year_columns) return;
  const temporal = studyTemporalIndicator(_activeExposome);
  if (
    temporalSeriesRequiresSpatialDetail(_activeExposome)
    && !temporalSeriesSpatiallyComplete(_activeExposome)
  ) {
    tabs.innerHTML = "";
    _currentYearTab = null;
    return;
  }
  const years = Object.keys(expo.year_columns)
    .filter((y) => studyHasColumn(expo.year_columns[y]))
    .sort();
  if (!_currentYearTab || !expo.year_columns[_currentYearTab]) {
    _currentYearTab = expo.year_columns[expo.default_year]
      ? expo.default_year
      : years[years.length - 1];
  }
  tabs.innerHTML = years
    .map(
      (y) => `
    <button
      type="button"
      class="year-tab"
      role="tab"
      data-year="${escHtml(y)}"
      data-active="${y === _currentYearTab ? "true" : "false"}"
      aria-selected="${y === _currentYearTab}"
    >${escHtml(y)}</button>`,
    )
    .join("");
  tabs.querySelectorAll(".year-tab").forEach((btn) => {
    btn.addEventListener("click", () => setYearTab(btn.dataset.year));
  });
}

async function setYearTab(year) {
  const temporal = studyTemporalIndicator(_activeExposome);
  if (
    temporalSeriesRequiresSpatialDetail(_activeExposome)
    && !temporalSeriesSpatiallyComplete(_activeExposome)
  ) return;
  const expo = getPalette().exposomes[_activeExposome];
  const col = expo?.year_columns?.[year];
  if (!col || year === _currentYearTab) return;
  _currentYearTab = year;
  renderYearTabs(expo);
  const { addChoropleth } = await import("./choropleth.js");
  await addChoropleth(_activeExposome, { column: col, yearLabel: String(year) });
  await refreshPanelValue(col);
}

// Repaint the choropleth with one vintage (`year`) or the aggregate
// column (`year === null`). Used by the time slider in column mode.
async function setYearColumn(year) {
  const temporal = studyTemporalIndicator(_activeExposome);
  if (
    temporalSeriesRequiresSpatialDetail(_activeExposome)
    && !temporalSeriesSpatiallyComplete(_activeExposome)
  ) return;
  const expo = getPalette().exposomes[_activeExposome];
  if (!expo?.year_columns) return;
  const col = year ? expo.year_columns[year] : expo.column;
  if (!col) return;
  _currentYearTab = year || null;
  const { addChoropleth } = await import("./choropleth.js");
  // Passing `column` explicitly for the aggregate bypasses addChoropleth's
  // own default_year resolution.
  await addChoropleth(
    _activeExposome,
    year ? { column: col, yearLabel: String(year) } : { column: col },
  );
  await refreshPanelValue(col);
}

// Sync legend marker + monitor + selected commune with the value the
// active column has for the commune currently shown in the side panel.
async function refreshPanelValue(col) {
  const slug = document.getElementById("communeProfileBody")?.dataset.communeSlug || _appState.commune;
  const profile = slug ? await getProfileBySlugCached(slug) : null;
  if (!profile) return;
  const [{ selectCommune, setLegendHighlight, getActiveFeatureProperties }, airchamber] = await Promise.all([
    import("./choropleth.js"),
    import("./visualizations/airchamber.js"),
  ]);
  selectCommune(slug);
  const v = profile.indicators?.[col] ?? getActiveFeatureProperties(slug)?.[col];
  if (typeof v === "number" && !Number.isNaN(v)) {
    setLegendHighlight(v);
    airchamber.setValue(v);
  } else {
    setLegendHighlight();
    airchamber.setValue(null);
  }
}

function showLoading(show, message, { error = false, retry = null, back = null } = {}) {
  const overlay = document.getElementById("loadingOverlay");
  if (!overlay) return;
  const text = overlay.querySelector(".loading-text");
  const actions = document.getElementById("loadingActions");
  const retryButton = document.getElementById("loadingRetry");
  const backButton = document.getElementById("loadingBack");
  if (text && message) {
    text.textContent = message;
    text.classList.toggle("loading-error", error);
  }
  overlay.classList.toggle("is-error", error);
  overlay.setAttribute("role", error ? "alert" : "status");
  overlay.setAttribute("aria-live", error ? "assertive" : "polite");
  if (actions) actions.hidden = !(show && (retry || back));
  if (retryButton) retryButton.onclick = retry;
  if (backButton) backButton.onclick = back;
  overlay.classList.toggle("visible", show);
}

// Expose for debugging.
window.__app = window.__app || {};
window.__app.getState = () => _state;
window.__app.getPalette = () => {
  // Import palette lazily (avoid circular import).
  return import("./palette.js").then((m) => m.getPalette());
};
window.__app.getMaster = () => {
  return import("./choropleth.js").then((m) => m.getMaster());
};
window.__app.showSidePanelForProfile = showSidePanelForProfile;
window.__app.getProfileBySlug = (slug) =>
  _profileCache.get(`${_currentStudyId || "legacy"}:${slug}`) || null;
window.__app.openLocationProfile = openLocationProfilePicker;
// Called by choropleth.setYear when a requested year has no annual
// GeoJSON yet (see docs/time_series_data.md). Gives the user visible
// feedback instead of failing silently in the console.
window.__app.notifyAnnualDataMissing = (year) => {
  const label = document.getElementById("timeSliderLabel");
  if (label) {
    label.textContent = `${year}: sin datos anuales aún`;
    label.classList.add("no-data");
  }
};
window.__app.setCommune = async ({ slug, centroid, name }) => {
  _appState = { ..._appState, commune: slug };
  setURLState(_appState);
  const map = getCommuneMap();
  if (!map) return;
  await navigateTo(map, centroid[0], centroid[1], { duration: 1100 });
  const profile = await getProfileBySlugCached(slug);
  if (profile) {
    await showSidePanelForProfile(profile);
    play("whoosh");
  }
  // Update the legend to show a marker at this commune's value.
  if (_activeExposome) {
    const palette = (await import("./palette.js")).getPalette();
    const expo = palette.exposomes[_activeExposome];
    if (expo) {
      const choropleth = await import("./choropleth.js");
      const column = activeExposomeColumn(expo);
      const v = profile?.indicators?.[column]
        ?? choropleth.getActiveFeatureProperties(slug)?.[column];
      if (typeof v === "number") {
        choropleth.selectCommune(slug);
        choropleth.setLegendHighlight(v);
        // Update airchamber with this commune's value for any exposome
        // (not just when hovering pixels — ensures NO₂ and others with no
        // fine layer also show a meaningful concentration in the chamber).
        import("./visualizations/airchamber.js").then((m) => m.setValue(v));
      }
    }
  }
};

async function getProfileBySlugCached(slug) {
  if (!slug) return null;
  const cacheKey = `${_currentStudyId || "legacy"}:${slug}`;
  if (_profileCache.has(cacheKey)) return _profileCache.get(cacheKey);
  const profile = await import("./click.js").then((m) => m.loadProfilePublic(slug));
  if (profile) _profileCache.set(cacheKey, profile);
  return profile;
}

async function updateOutcomePanel() {
  const { renderOutcomeAssociations } = await import("./panels/outcome-associations.js");
  await renderOutcomeAssociations(_activeExposome);
}

function renderCommuneExposomeSwitcher() {
  const container = document.getElementById("communeExposomeSwitcher");
  if (!container) return;
  const exposomes = getPalette().exposomes || {};
  const expo = exposomes[_activeExposome] || {};
  const parent = expo.parent ? exposomes[expo.parent] : null;
  const activeLabel = parent?.label ? `${parent.label}: ${expo.label || _activeExposome}` : expo.label || _activeExposome;
  const activeKind = expo.category === "resultados" ? "Resultado activo" : "Exposoma activo";
  container.innerHTML = `
    <button
      class="commune-exposome-menu-button"
      id="communeExposomeMenuButton"
      type="button"
      aria-haspopup="dialog"
    >
      <span class="commune-exposome-menu-kicker">${activeKind}</span>
      <span class="commune-exposome-menu-main">
        <span>${escHtml(activeLabel)}</span>
        <span>${escHtml(expo.unit || "")}</span>
      </span>
      <span class="commune-exposome-menu-action">Cambiar exposoma</span>
    </button>
  `;
  container.querySelector("#communeExposomeMenuButton")?.addEventListener("click", openCommuneExposomeMenu);
}

async function openCommuneExposomeMenu() {
  const { initCityOverviewPanel, showCityOverview, hideCityOverview } = await import("./panels/city-overview.js");
  initCityOverviewPanel(
    async (exposomeId) => {
      hideCityOverview();
      showBackButton(true);
      await switchExposome(exposomeId);
    },
    () => {
      hideCityOverview();
      showBackButton(true);
    },
  );
  showCityOverview("Cambiar exposoma", currentCityStats(), {
    mode: "switch",
    backLabel: "\u2190 Perfil",
  });
  // While the overlay is open its "\u2190 Perfil" is the only escape hatch;
  // the header back reappears when the overlay closes.
  showBackButton(false);
}

function currentCityStats() {
  return getCityRecord(_currentCity) || {};
}

function resolveSelectableExposomeId(exposomeId) {
  const exposomes = getPalette()?.exposomes || {};
  const requested = exposomes[exposomeId] ? exposomeId : "pm25";
  const expo = exposomes[requested];
  if (expo?.status === "ready") return requested;
  const childIds = Array.isArray(expo?.children)
    ? expo.children
    : Object.entries(exposomes)
        .filter(([, e]) => e.parent === requested)
        .map(([id]) => id);
  const firstReadyChild = childIds.find((id) => exposomes[id]?.status === "ready");
  if (firstReadyChild) return firstReadyChild;
  return exposomes.pm25?.status === "ready" ? "pm25" : requested;
}

async function switchExposome(exposomeId) {
  const palette = getPalette();
  const nextExposomeId = resolveSelectableExposomeId(exposomeId);
  const expo = palette.exposomes[nextExposomeId];
  if (!expo || expo.status !== "ready") return;

  _activeExposome = nextExposomeId;
  _currentYearTab = null; // renderYearTabs re-resolves the default vintage
  _appState = { ..._appState, exposome: nextExposomeId };
  setURLState(_appState);
  renderCommuneExposomeSwitcher();
  // Restore the previous exposome's slider state (playback, pm25 annual
  // data) before rendering the new exposome's slider/tabs.
  resetTimeSliderState();
  updateTimeSliderVisibility(true);

  const [{ addChoropleth, selectCommune, setLegendHighlight }, airchamber] = await Promise.all([
    import("./choropleth.js"),
    import("./visualizations/airchamber.js"),
  ]);

  const currentExposome = await addChoropleth(nextExposomeId);
  airchamber.setChamberCopy(currentExposome);
  await updateOutcomePanel();

  const slug = document.getElementById("communeProfileBody")?.dataset.communeSlug || _appState.commune;
  const profile = slug ? await getProfileBySlugCached(slug) : null;

  if (profile) {
    await showSidePanelForProfile(profile);
    selectCommune(slug);
    const { getActiveFeatureProperties } = await import("./choropleth.js");
    const column = activeExposomeColumn(expo);
    const v = profile.indicators?.[column] ?? getActiveFeatureProperties(slug)?.[column];
    if (typeof v === "number" && !Number.isNaN(v)) {
      setLegendHighlight(v);
      airchamber.setValue(v);
    } else {
      setLegendHighlight();
      airchamber.setValue(null);
    }
  } else {
    setLegendHighlight();
    airchamber.setValue(null);
    await renderExposomeInfoTabs(nextExposomeId);
  }
}

async function showSidePanelForProfile(profile) {
  // The profile is now split into 2 sections:
  //   1. commune-profile-collapsible: commune summary (closed by default)
  //   2. info-tabs-content: 4 horizontal tabs (Fuente, Specs, Metodología, Citación)
  const profileBody = document.getElementById("communeProfileBody");
  const profileSummary = document.getElementById("communeProfileSummary");
  const legacySidePanel = document.getElementById("sidePanel");
  if (!profileBody) return;
  if (profile?.slug) {
    _profileCache.set(`${_currentStudyId || "legacy"}:${profile.slug}`, profile);
  }

  const clusterLabel = profile.cluster?.label || "-";
  const ebiScore = profile.ebi?.score?.toFixed(3) ?? "-";
  const ebiRank = profile.ebi?.rank ?? "-";
  const lisaQuad = profile.lisa_quadrant || "-";
  const indicatorRows = Object.entries(profile.indicators || {})
    .slice(0, 20)
    .map(
      ([k, v]) =>
        `<tr><td>${k}</td><td>${typeof v === "number" ? v.toFixed(2) : v}</td></tr>`,
    )
    .join("");
  const subCommuneHtml = renderSubCommuneDetail(profile.indicators || {});

  // Collapsible summary: commune name + badges.
  if (profileSummary) {
    profileSummary.innerHTML = `
      <span class="commune-name">${escHtml(profile.name)}</span>
      <span class="commune-badges">
        <span class="badge">${escHtml(clusterLabel)}</span>
        <span class="badge">EBI: ${ebiScore}</span>
        <span class="badge">Rank: ${ebiRank}</span>
        <span class="badge">LISA: ${escHtml(lisaQuad)}</span>
      </span>
    `;
  }

  // Mini-chart: annual time series for the active exposome (if available).
  const timeseries = profile.timeseries?.[_activeExposome] || [];
  const miniChartHtml = timeseries.length > 0 ? renderMiniChart(timeseries, _currentYear) : "";
  const expoLabel = getPalette()?.exposomes?.[_activeExposome]?.label || _activeExposome;

  // Profile body: mini-chart (if has data) + top 20 indicators + sub-commune detail.
  profileBody.innerHTML = `
    ${timeseries.length > 0 ? `<h3>Serie temporal ${expoLabel} (anual)</h3>${miniChartHtml}` : ""}
    <h3>Perfil (top 20)</h3>
    <table>${indicatorRows}</table>
    ${subCommuneHtml}
  `;
  profileBody.dataset.communeSlug = profile.slug;

  // Render exposome info into the 4 tabs.
  await renderExposomeInfoTabs(_activeExposome, profile.indicators || {});

  // Wire copy-bibtex buttons (if any).
  const copyBtn = document.querySelector(".copy-bibtex");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const bib = document.querySelector(".bibtex");
      if (bib) {
        navigator.clipboard?.writeText(bib.textContent);
        copyBtn.textContent = "Copiado!";
        setTimeout(() => (copyBtn.textContent = "Copiar BibTeX"), 1500);
      }
    });
  }

  // Wire the horizontal tabs once (the buttons are static in index.html;
  // re-wiring on every profile render stacked duplicate listeners).
  const tablist = document.querySelector(".info-tabs");
  if (tablist && tablist.dataset.wired !== "1") {
    tablist.dataset.wired = "1";
    const tabs = Array.from(tablist.querySelectorAll(".info-tab"));
    const selectTab = (btn) => {
      tabs.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", active ? "true" : "false");
        b.tabIndex = active ? 0 : -1;
      });
      showInfoTab(btn.dataset.tab);
    };
    tabs.forEach((b) => {
      b.tabIndex = b.classList.contains("active") ? 0 : -1;
      b.addEventListener("click", () => selectTab(b));
    });
    // WAI-ARIA tabs pattern: roving tabindex + arrow-key navigation.
    tablist.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const current = tabs.indexOf(document.activeElement);
      if (current === -1) return;
      e.preventDefault();
      const delta = e.key === "ArrowRight" ? 1 : -1;
      const next = tabs[(current + delta + tabs.length) % tabs.length];
      next.focus();
      selectTab(next);
    });
  }

  // Also keep the legacy side panel in sync so the CSS-based classes
  // (which style the .side-panel descendants) still apply, even though
  // the side panel is hidden in the new layout.
  if (legacySidePanel) {
    const content = document.getElementById("sidePanelContent");
    if (content) {
      content.innerHTML = `
        <h2>${escHtml(profile.name)}</h2>
        <p>
          <span class="badge">${escHtml(clusterLabel)}</span>
          <span class="badge">EBI: ${ebiScore}</span>
          <span class="badge">Rank: ${ebiRank}</span>
          <span class="badge">LISA: ${escHtml(lisaQuad)}</span>
        </p>
        <h3>Perfil (top 20)</h3>
        <table>${indicatorRows}</table>
        ${subCommuneHtml}
      `;
    }
    legacySidePanel.classList.add("open");
  }
}

function showInfoTab(tabId) {
  const container = document.getElementById("infoTabsContent");
  if (!container) return;
  const sections = container.querySelectorAll(".info-section");
  sections.forEach((s) => {
    s.style.display = s.dataset.tab === tabId ? "block" : "none";
  });
}

// Render a small SVG line chart of PM2.5 annual values for a commune.
// data: [{year, value}, ...] sorted by year.
// currentYear: "avg" (default) or a specific year to highlight.
function renderMiniChart(data, currentYear) {
  if (!data || !data.length) {
    return '<p class="mini-chart-empty">Serie temporal anual no disponible. '
      + 'Ver <code>docs/time_series_data.md</code>.</p>';
  }
  const w = 280, h = 90, padL = 28, padR = 8, padT = 10, padB = 18;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const values = data.map((d) => d.value).filter((v) => typeof v === "number");
  if (!values.length) {
    return '<p class="mini-chart-empty">Sin valores validos.</p>';
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = data.map((d, i) => {
    const x = padL + (i / Math.max(1, data.length - 1)) * innerW;
    const y = padT + (1 - (d.value - min) / range) * innerH;
    return { x, y, year: d.year, value: d.value };
  });
  const pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  // Highlight current year (if it matches a data point).
  const highlightIdx = (currentYear && currentYear !== "avg")
    ? data.findIndex((d) => d.year === currentYear)
    : -1;
  const highlight = highlightIdx >= 0 ? pts[highlightIdx] : null;
  // Y axis ticks (min, mid, max).
  const fmt = (v) => v.toFixed(0);
  const yTicks = [
    { y: padT, v: max },
    { y: padT + innerH / 2, v: (min + max) / 2 },
    { y: padT + innerH, v: min },
  ];
  const yTickSvg = yTicks.map(
    (t) => `<line x1="${padL - 2}" y1="${t.y.toFixed(1)}" x2="${padL}" y2="${t.y.toFixed(1)}" stroke="#94b0c2" stroke-width="1"/>`
      + `<text x="${padL - 4}" y="${(t.y + 3).toFixed(1)}" text-anchor="end" font-family="VT323" font-size="9" fill="#94b0c2">${fmt(t.v)}</text>`,
  ).join("");
  // X axis labels (every other year to avoid clutter).
  const xLabels = pts.map((p, i) => {
    const show = i === 0 || i === pts.length - 1 || i === Math.floor(pts.length / 2);
    if (!show) return "";
    return `<text x="${p.x.toFixed(1)}" y="${h - 4}" text-anchor="middle" font-family="VT323" font-size="9" fill="#94b0c2">${p.year}</text>`;
  }).join("");
  return `
    <svg class="mini-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">
      ${yTickSvg}
      ${xLabels}
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + innerH}" stroke="#94b0c2" stroke-width="1" opacity="0.5"/>
      <line x1="${padL}" y1="${padT + innerH}" x2="${w - padR}" y2="${padT + innerH}" stroke="#94b0c2" stroke-width="1" opacity="0.5"/>
      <path d="${pathD}" fill="none" stroke="#ff77a8" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${pts.map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="2.5" fill="#c4d4e4" stroke="#0d0e1a" stroke-width="0.5"/>`).join("")}
      ${highlight ? `<circle cx="${highlight.x.toFixed(1)}" cy="${highlight.y.toFixed(1)}" r="4" fill="#ff77a8" stroke="#0d0e1a" stroke-width="1.5"/>
        <text x="${highlight.x.toFixed(1)}" y="${(highlight.y - 6).toFixed(1)}" text-anchor="middle" font-family="VT323" font-size="11" fill="#ff77a8" font-weight="bold">${highlight.value.toFixed(1)}</text>` : ""}
    </svg>
  `;
}

// Populate the profile download select with all 52 communes.
async function populateProfileSelect() {
  const sel = document.getElementById("profileDownloadSelect");
  const link = document.getElementById("profileDownloadLink");
  if (!sel || !link) return;
  try {
    const data = getMaster();
    if (!data || !data.features) throw new Error("master not loaded");
    const unitWord = spatialUnitLabel(getStudyManifest()?.spatial?.unit_type);
    sel.innerHTML = `<option value="">Seleccionar ${unitWord}...</option>`;
    // Sort by name for predictability.
    const features = [...data.features].sort((a, b) =>
      a.properties.name.localeCompare(b.properties.name),
    );
    for (const f of features) {
      const opt = document.createElement("option");
      opt.value = f.properties.slug;
      opt.textContent = f.properties.name;
      sel.appendChild(opt);
    }
    sel.addEventListener("change", () => {
      if (sel.value) {
        link.href = assetUrl(`profiles/${sel.value}.json`) || `/data/profiles/${sel.value}.json`;
        link.download = `${sel.value}.json`;
        link.style.display = "inline-block";
        link.textContent = `Descargar ${sel.options[sel.selectedIndex].textContent}.json`;
      } else {
        link.style.display = "none";
      }
    });
  } catch (e) {
    sel.innerHTML = '<option value="">Error cargando comunas</option>';
    console.warn("populateProfileSelect failed:", e);
  }
}

async function renderMethodologySection(exposomeId) {
  try {
    const dataLayerId = exposomeDataId(exposomeId);
    const res = await fetch(
      assetUrl(`methodology/${dataLayerId}.json`) || `/data/methodology/${dataLayerId}.json`,
    );
    if (!res.ok) return "<p>Metodología no disponible.</p>";
    const doc = await res.json();
    const sections = doc.sections || [];
    return sections.map((s) => {
      const body = (s.body || []).join("\n").trim();
      if (!body) return "";
      const tag = s.level === 1 ? "h4" : "h5";
      return `<${tag}>${escHtml(s.title)}</${tag}><p>${escHtml(body)}</p>`;
    }).filter(Boolean).join("\n") || "<p>Metodología no disponible.</p>";
  } catch (e) {
    return "<p>No se pudo cargar la metodologia.</p>";
  }
}

async function renderExposomeInfoTabs(exposomeId, profileIndicators = null) {
  const container = document.getElementById("infoTabsContent");
  if (!container) return;
  const expo = getPalette().exposomes[exposomeId] || {};
  const manifest = getStudyManifest();
  const cityLabel = manifest?.location?.country
    ? `${manifest.location.name}, ${manifest.location.country}`
    : manifest?.location?.name || "la ciudad";
  const unitWord = spatialUnitLabel(manifest?.spatial?.unit_type);
  const unitPlural = spatialUnitLabel(manifest?.spatial?.unit_type, { plural: true });
  const unitArticle = unitWord.endsWith("a") ? "una" : "un";
  const nUnits = manifest?.spatial?.expected_units;
  const unitsLabel = nUnits ? `${nUnits} ${nUnits === 1 ? unitWord : unitPlural}` : unitPlural;
  const nColumns = manifest?.columns?.length || 0;
  const activeYear = expo.year_columns
    ? (_currentYearTab || expo.default_year || null)
    : null;
  const spatialOptions = activeYear ? { year: String(activeYear) } : undefined;
  const hasFineLayer = studyHasFineLayer(exposomeId, spatialOptions);
  const spatial = studySpatialIndicator(exposomeId, spatialOptions);
  const detailAsset = studyDetailAsset(exposomeId, spatialOptions);
  const supportText = spatialSupportText(spatial, expo.resolution || unitWord);
  const sourceId = expo.source_id || expo.parent || exposomeId;
  const methodologyId = exposomeDataId(expo.methodology_id || expo.parent || exposomeId);
  let src = null;
  try {
    const sourcesRes = await fetch(studyAsset("sources") || "/data/sources.json");
    if (sourcesRes.ok) {
      const sources = await sourcesRes.json();
      const sourceMap = sources.sources || sources;
      src = sourceMap[exposomeId] || sourceMap[sourceId] || sourceMap[exposomeDataId(exposomeId)];
    }
  } catch (e) {
    console.warn("renderExposomeInfoTabs failed:", e);
  }
  if (!src) {
    container.innerHTML = '<p class="right-panel-empty">Sin info del exposoma.</p>';
    return;
  }
  // Load methodology content asynchronously alongside the rest.
  const metodologiaHtml = await renderMethodologySection(methodologyId);
  const paper = src.paper || "n/a";
  const doi = src.doi || "";
  const doiStatus = doi
    ? "Verificado"
    : src.doi_status === "not_assigned"
      ? "No asignado por la fuente"
      : "";
  const coverageColumn = expo.coverage_column;
  const coverageValue = coverageColumn && profileIndicators
    ? profileIndicators[coverageColumn]
    : null;
  const coverageDetail = coverageValue === 0
    ? "Esta comuna está fuera del perímetro modelado; los valores cero indican sin estimación modelada."
    : "";
  const coverageNote = expo.coverage_note || src.coverage_note || "";
  const coverageHtml = coverageNote
    ? `<p class="coverage-note"><strong>Cobertura:</strong> ${escHtml(coverageNote)}${coverageDetail ? ` ${escHtml(coverageDetail)}` : ""}</p>`
    : "";
  // Prefer the curated BibTeX emitted by the layer-info registry; the
  // client-side fallback only fires for legacy bundles without one.
  const bibtex = src.bibtex || (doi
    ? `@article{${(src.name?.split(" ")[0] || "x").toLowerCase()}${new Date().getFullYear()},
  title = {${paper}},
  doi = {${doi}},
}`
    : "No BibTeX available.");

  // Render all 4 sections; show only the first (fuente) by default.
  container.innerHTML = `
    <div class="info-section" data-tab="fuente">
      <h4>Fuente de datos</h4>
      <p><strong>${escHtml(src.name)}</strong></p>
      ${src.url ? `<p>URL: <a href="${escHtml(src.url)}" target="_blank" rel="noopener">${escHtml(src.url)}</a></p>` : ""}
      <p>Licencia: ${escHtml(src.license || "?")}</p>
      ${src.paper ? `<p>Paper: ${escHtml(src.paper)}</p>` : ""}
      ${src.doi ? `<p>DOI: <a href="https://doi.org/${escHtml(src.doi)}" target="_blank" rel="noopener">${escHtml(src.doi)}</a></p>` : ""}
      ${!src.doi && doiStatus ? `<p>DOI: ${escHtml(doiStatus)}</p>` : ""}
      ${coverageHtml}
    </div>
    <div class="info-section" data-tab="specs" style="display:none">
      <h4>Especificaciones</h4>
      <table class="specs-table">
        ${src.spatial_resolution ? `<tr><td>Resolucion espacial</td><td>${escHtml(src.spatial_resolution)}</td></tr>` : ""}
        ${src.temporal_coverage ? `<tr><td>Cobertura temporal</td><td>${escHtml(src.temporal_coverage)}</td></tr>` : ""}
        ${src.validation ? `<tr><td>Validacion</td><td>${escHtml(src.validation)}</td></tr>` : ""}
        ${coverageColumn ? `<tr><td>Campo cobertura</td><td>${escHtml(coverageColumn)}</td></tr>` : ""}
      </table>
      ${coverageHtml}
    </div>
    <div class="info-section" data-tab="metodologia" style="display:none">
      <h4>Metodología</h4>
      ${metodologiaHtml}
    </div>
    <div class="info-section" data-tab="citacion" style="display:none">
      <h4>Citación</h4>
      <p><strong>Paper:</strong> ${escHtml(paper)}</p>
      ${doi ? `<p><strong>DOI:</strong> <a href="https://doi.org/${escHtml(doi)}" target="_blank" rel="noopener">${escHtml(doi)}</a></p>` : ""}
      ${!doi && doiStatus ? `<p><strong>DOI:</strong> ${escHtml(doiStatus)}</p>` : ""}
      <pre class="bibtex">${escHtml(bibtex)}</pre>
      <button class="copy-bibtex" type="button">Copiar BibTeX</button>
    </div>
    <div class="info-section" data-tab="descargar" style="display:none">
      <h4>Descargar datos</h4>
      <p>Este dataset contiene la exposición ambiental de ${unitsLabel}
      de ${escHtml(cityLabel)}, con indicadores
      de aire, luz, clima, cobertura verde, servicios urbanos,
      sociedad, toxinas y exposoma compuesto (EBI).</p>

      <h5>Datos maestros (${unitsLabel}${nColumns ? ` x ${nColumns} cols` : ""})</h5>
      <ul class="download-list">
        <li><a href="${escHtml(studyAsset("master_geojson") || "/data/master.geojson")}" download>master.geojson</a> — geometria + valores</li>
        <li><a href="${escHtml(studyAsset("master_csv") || "/data/master.csv")}" download>master.csv</a> — solo valores</li>
        <li><a href="${escHtml(assetUrl("profiles_meta/profiles.json") || "/data/profiles_meta/profiles.json")}" download>profiles_meta/profiles.json</a> — índice de los perfiles</li>
      </ul>

      ${hasFineLayer && detailAsset ? `
      <h5>Detalle espacial publicado</h5>
      <ul class="download-list">
        <li><a href="${escHtml(assetUrl(detailAsset.path))}" download>${escHtml(detailAsset.path)}</a></li>
      </ul>
      ` : ""}

      <h5>Perfiles por ${unitWord} (${unitsLabel})</h5>
      <p>Selecciona ${unitArticle} ${unitWord} para descargar su perfil completo
      (cluster, EBI, LISA, indicators, neuro outcomes):</p>
      <select id="profileDownloadSelect" class="profile-select">
        <option value="">Cargando...</option>
      </select>
      <a id="profileDownloadLink" class="button-link" href="#" download style="display:none">Descargar perfil</a>

      <h4>Documentacion</h4>
      <table class="specs-table">
        <tr><td>Unidades</td><td>${escHtml(expo.unit ? `${expo.label}: ${expo.unit}` : expo.label || "ver fuente")}</td></tr>
        <tr><td>Soporte espacial</td><td>${escHtml(supportText)}${hasFineLayer ? " (detalle publicado)" : " (solo agregado publicado)"}</td></tr>
        <tr><td>Fuente</td><td>${escHtml(src.name || "ver pestaña Fuente")}</td></tr>
        ${coverageNote ? `<tr><td>Cobertura</td><td>${escHtml(coverageNote)}</td></tr>` : ""}
        <tr><td>Metodología</td><td>Ver pestaña Metodología</td></tr>
        <tr><td>Generado</td><td>GEMMA — Global Exposome Modeling, Mapping & Analytics</td></tr>
      </table>
    </div>
  `;
  // Populate the profile download select.
  populateProfileSelect();
}

function exposomeDataId(id) {
  return id === "pm25" ? "air_quality_pm25" : id;
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Render the "sub-commune detail" block using per-commune stats
// already present in the master: max, std, percentiles, n_grid.
// Falls back gracefully when a stat is not available.
function renderSubCommuneDetail(indicators) {
  // Pick exposomes that have intra-commune stats already in the
  // master. Each entry: [label, mean_key, max_key, std_key, p95_key,
  // n_grid_key, unit, type]. type=std | max | p95.
  const STATS = [
    {
      label: "ALAN",
      mean: "alan_radiance_mean",
      sd: "alan_radiance_sd",
      max: "alan_radiance_max",
      n: null,
      unit: "nW/cm²/sr",
      desc: "Dispersión intra-commune de luz artificial nocturna",
    },
    {
      label: "NDVI",
      mean: "ndvi_mean",
      sd: null,
      max: "ndvi_max",
      n: null,
      unit: "",
      desc: "Rango de cobertura vegetal intra-commune",
    },
    {
      label: "Viento (p99)",
      mean: "wind_speed_mean",
      sd: null,
      max: "wind_speed_max_p99",
      n: null,
      unit: "m/s",
      desc: "Percentil 99 de velocidad del viento (eventos extremos)",
    },
    {
      label: "Viento invierno (p99)",
      mean: "wind_speed_mean_winter",
      sd: null,
      max: "wind_speed_max_p99_winter",
      n: null,
      unit: "m/s",
      desc: "Percentil 99 de viento en invierno",
    },
    {
      label: "Fire brightness (max)",
      mean: null,
      sd: null,
      max: "fire_brightness_max_k",
      n: null,
      unit: "K",
      desc: "Temperatura máxima de fuego detectado",
    },
    {
      label: "Dist. salud (p90)",
      mean: "mean_nearest_health_m",
      sd: null,
      max: "p90_nearest_health_m",
      n: null,
      unit: "m",
      desc: "p90 de distancia al centro de salud más cercano",
    },
    {
      label: "Grid health",
      mean: null,
      sd: null,
      max: null,
      n: "health_n_access_grid",
      unit: "cells",
      desc: "Celdas de grilla con cobertura de salud",
    },
    {
      label: "Grid social",
      mean: null,
      sd: null,
      max: null,
      n: "social_n_access_grid",
      unit: "cells",
      desc: "Celdas de grilla con infraestructura social",
    },
    {
      label: "Grid climate",
      mean: null,
      sd: null,
      max: null,
      n: "climate_n_area_grid_points",
      unit: "pts",
      desc: "Puntos de grilla climática dentro de la commune",
    },
  ];

  const fmt = (v) => (typeof v === "number" && !isNaN(v) ? v.toFixed(2) : "—");
  const rows = STATS.map((s) => {
    const mean = s.mean ? indicators[s.mean] : null;
    const max = s.max ? indicators[s.max] : null;
    const sd = s.sd ? indicators[s.sd] : null;
    const n = s.n ? indicators[s.n] : null;
    // Build a mini bar showing mean vs max if both exist.
    let barHtml = "";
    if (
      typeof mean === "number" &&
      typeof max === "number" &&
      max > 0
    ) {
      const t = Math.max(0, Math.min(1, mean / max));
      const w = Math.max(5, Math.min(100, t * 100));
      barHtml = `<div class="mini-boxplot"><div class="bp-bar" style="width:${w}%"></div><div class="bp-cap"></div></div>`;
    } else if (typeof n === "number") {
      // grid count as a chip
      barHtml = `<div class="mini-grid-count">${n.toFixed(0)}</div>`;
    }
    return `
      <tr>
        <td class="sub-label">${s.label}</td>
        <td class="sub-stats">
          ${
            typeof mean === "number"
              ? `<span class="value-current">${fmt(mean)}</span>`
              : "—"
          }
          ${
            typeof max === "number"
              ? `<span class="sub-max">max ${fmt(max)}</span>`
              : ""
          }
          ${
            typeof sd === "number"
              ? `<span class="sub-sd">sd ${fmt(sd)}</span>`
              : ""
          }
        </td>
        <td class="sub-bar">${barHtml}</td>
      </tr>
    `;
  }).join("");

  return `
    <details class="sub-commune-detail" open>
      <summary>
        <span class="sub-arrow">▾</span>
        Detalle sub-comuna (resolucion de grilla)
      </summary>
      <p class="sub-help">
        Distribucion de indicadores dentro de la commune.
        "mean" es el promedio; "max" / "sd" muestran la dispersion interna
        calculada sobre los pixeles / grilla de la commune.
      </p>
      <table class="sub-table">${rows}</table>
    </details>
  `;
}

main();
