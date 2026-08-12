import { DEFAULT_TWEEN_MS, WHO_THRESHOLDS } from "./constants.js";
import { advanceTween } from "./transitions.js";
import { updateCopy, updateNumericDisplay, updatePreviewCopy, resetDisplay } from "./dom.js";
import { createPixiApp, destroyPixiApp, getBounds } from "./pixiApp.js";
import { createRendererForExposome } from "./registry.js";
import { getDisplayValue, valueToVisualState } from "./scaling.js";
import { getThemeForExposome } from "./theme.js";
import { prefersReducedMotion } from "../../utils/motion.js";
import {
  clearReactiveIntensity,
  setActiveAmbient,
  setReactiveIntensity,
  stopAmbient,
} from "../../sound.js";

let _pixi = null;
let _expo = null;
let _theme = null;
let _renderer = null;
let _rendererId = null;
let _rendererInitialized = false;
let _baseValue = null;
let _previewContext = null;
let _baseDomain = null;
let _targetState = valueToVisualState(null);
let _currentState = valueToVisualState(null);
let _tween = null;
let _ticker = null;

export async function init(containerId = "airchamberCanvas") {
  const container = document.getElementById(containerId);
  if (!container) {
    console.warn(`initAirchamber: container #${containerId} not found`);
    return null;
  }
  destroy();
  _pixi = await createPixiApp(container);
  if (!_pixi) return null;
  configure(_expo || defaultExpo());
  // Reduced motion: skip the continuous loop. The scene's fixed elements
  // stay visible via one static frame per state change (updateFromValue);
  // PIXI's own ticker keeps presenting the unchanged stage.
  if (!prefersReducedMotion()) {
    _ticker = (ticker) => tick(ticker);
    _pixi.app.ticker.add(_ticker);
  }
  return _pixi.app;
}

export function destroy() {
  if (_pixi?.app && _ticker) {
    try { _pixi.app.ticker.remove(_ticker); } catch (_) {}
  }
  _ticker = null;
  destroyRenderer();
  destroyPixiApp(_pixi);
  _pixi = null;
  _baseValue = null;
  _previewContext = null;
  _baseDomain = null;
  _targetState = valueToVisualState(null);
  _currentState = valueToVisualState(null);
  _tween = null;
  stopAmbient();
  resetDisplay();
}

export function configure(expo) {
  _expo = normalizeExpo(expo);
  _theme = getThemeForExposome(_expo);
  setActiveAmbient(_expo);
  updateCopy(_expo);
  const next = createRendererForExposome(_expo);
  if (!_pixi) {
    destroyRenderer();
    _rendererId = next.id;
    updateFromValue(displayValue(), false);
    return;
  }
  if (next.id !== _rendererId) {
    destroyRenderer();
    _rendererId = next.id;
    _renderer = next.renderer;
    _renderer.init({
      parent: _pixi.root,
      theme: _theme,
      bounds: getBounds(_pixi),
    });
    _rendererInitialized = true;
  } else if (!_renderer || !_rendererInitialized) {
    if (!_renderer) _renderer = next.renderer;
    _renderer.init({
      parent: _pixi.root,
      theme: _theme,
      bounds: getBounds(_pixi),
    });
    _rendererInitialized = true;
  }
  updateFromValue(displayValue(), false);
}

export function setValue(value) {
  const previousValue = displayValue();
  _baseValue = value;
  _previewContext = null;
  updateCopy(_expo);
  updateFromValue(value, previousValue !== value);
}

export function previewValue(value, context = {}) {
  const previousValue = displayValue();
  _previewContext = { value, ...context };
  updatePreviewCopy(_expo, _previewContext);
  updateFromValue(value, previousValue !== value);
}

export function clearPreviewValue() {
  if (_previewContext == null) return;
  const previousValue = _previewContext.value;
  _previewContext = null;
  updateCopy(_expo);
  updateFromValue(_baseValue, previousValue !== _baseValue);
}

// Per-study value domain for the active exposome's column (see
// choropleth.js computeStudyDomain). Lets the chamber discriminate across
// whichever city is loaded instead of clamping to Santiago-tuned palette
// bounds (see scaling.js resolveStudyBounds for the fallback chain). May
// arrive after configure()/setValue() already painted a frame, so it
// forces one corrective re-render without animating.
export function setStudyDomain(stats) {
  _baseDomain = stats || null;
  updateFromValue(displayValue(), false);
}

export function getStateForTests() {
  return {
    rendererId: _rendererId,
    baseValue: _baseValue,
    previewValue: _previewContext?.value ?? null,
    previewContext: _previewContext ? { ..._previewContext } : null,
    baseDomain: _baseDomain,
    effectiveDomain: activeDomain(),
    hasPixi: !!_pixi,
  };
}

function updateFromValue(value, animate = true) {
  _targetState = valueToVisualState(value, _expo || defaultExpo(), activeDomain());
  if (typeof value === "number" && Number.isFinite(value)) {
    setReactiveIntensity(_targetState.intensity);
  } else {
    clearReactiveIntensity();
  }
  if (!_pixi || !animate || prefersReducedMotion()) {
    _tween = null;
    _currentState = { ..._targetState };
    updateNumericDisplay({
      value: displayValue(),
      visualCount: _currentState.visualCount,
    });
    renderStaticFrame();
    return;
  }
  const now = performance.now();
  _tween = {
    startedAt: now,
    durationMs: DEFAULT_TWEEN_MS,
    from: { ..._currentState },
    to: { ..._targetState },
  };
  updateNumericDisplay({
    value: displayValue(),
    visualCount: _currentState.visualCount,
  });
}

function displayValue() {
  return getDisplayValue(_baseValue, _previewContext?.value);
}

function activeDomain() {
  return _previewContext?.domain || _baseDomain;
}

function tick() {
  if (!_pixi || !_renderer) return;
  const now = performance.now();
  if (_tween) {
    const countTween = advanceTween({
      from: _tween.from.visualCount || 0,
      to: _tween.to.visualCount || 0,
      startedAt: _tween.startedAt,
      durationMs: _tween.durationMs,
      now,
    });
    const intensityTween = advanceTween({
      from: _tween.from.intensity || 0,
      to: _tween.to.intensity || 0,
      startedAt: _tween.startedAt,
      durationMs: _tween.durationMs,
      now,
    });
    _currentState = {
      ..._targetState,
      visualCount: countTween.value,
      intensity: intensityTween.value,
      density: intensityTween.value,
      diffusion: intensityTween.value,
      radiance: intensityTween.value,
      acoustic: intensityTween.value,
    };
    if (countTween.done && intensityTween.done) {
      _currentState = { ..._targetState };
      _tween = null;
    }
  }
  const bounds = getBounds(_pixi);
  _renderer.update({
    bounds,
    theme: _theme || getThemeForExposome(_expo),
    visualState: _currentState,
    now,
  });
  updateNumericDisplay({
    value: displayValue(),
    visualCount: _currentState.visualCount,
  });
}

// One update() pass at the current target state. Renderers only lay out
// and draw inside update(), so without the continuous ticker (reduced
// motion) each state change needs exactly one of these.
function renderStaticFrame() {
  if (!_pixi || !_renderer) return;
  _renderer.update({
    bounds: getBounds(_pixi),
    theme: _theme || getThemeForExposome(_expo),
    visualState: _currentState,
    now: performance.now(),
  });
}

function destroyRenderer() {
  try { _renderer?.destroy?.(); } catch (_) {}
  _renderer = null;
  _rendererId = null;
  _rendererInitialized = false;
}

function normalizeExpo(expo) {
  if (!expo) return defaultExpo();
  return {
    id: expo.id || inferId(expo),
    ...expo,
  };
}

function inferId(expo) {
  const label = String(expo?.label || "").toLowerCase();
  if (label.includes("no")) return "no2";
  if (label.includes("alan")) return "alan";
  return "pm25";
}

function defaultExpo() {
  return {
    id: "pm25",
    label: "PM2.5",
    unit: "µg/m³",
    chamber: {
      value_label: "PM2.5:",
      unit: "µg/m³",
      count_label: "Particulas visibles",
      scene_label: "PM2.5",
      scene_sublabel: "sensor de aire",
      scale_note: "Display = sensor ambiental | Densidad = carga relativa",
      particle_color: "0x6E8794",
    },
  };
}

// Absolute health category, independent of the study's own data range —
// unlike the chamber's visual intensity (hybrid, see setStudyDomain), this
// stays anchored to fixed thresholds so "bueno" means the same thing in
// every city. Defaults to the WHO PM2.5 bands; other exposomes can opt in
// via an `expo.thresholds` block in palette.json (same shape).
export function whoCategory(value, expo = null) {
  if (typeof value !== "number" || Number.isNaN(value) || value < 0) return null;
  const thresholds = expo?.thresholds || WHO_THRESHOLDS;
  if (value < thresholds.bueno) return "bueno";
  if (value < thresholds.moderado) return "moderado";
  if (value < thresholds.no_saludable) return "no_saludable";
  return "muy_no_saludable";
}

export function whoCategoryLabel(cat) {
  return {
    bueno: "Bueno",
    moderado: "Moderado",
    no_saludable: "No saludable",
    muy_no_saludable: "Muy no saludable",
  }[cat] || "-";
}
