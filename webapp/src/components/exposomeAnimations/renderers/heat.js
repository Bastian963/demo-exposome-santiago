import { Container, Graphics } from "pixi.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { clamp01 } from "../transitions.js";
import { isMeasuredValue, segmentedCount } from "../monitorSemantics.js";
import { drawUnavailableState } from "../primitives/monitorState.js";
import {
  getUrbanSceneRect,
  getGroundY,
  drawThermalSkyline,
  drawSunDisc,
  drawMoon,
  drawStars,
  drawConvectionShimmer,
  drawRadiantGlow,
  drawWarmWindows,
  drawHorizontalThermometer,
  drawTwilightDivider,
  seeded,
} from "../primitives/pixelThermalCity.js";

const COLORS = {
  amber: 0xd9a441,
  cool: 0x27395d,
  deepNight: 0x09111f,
  panel: 0x0c1422,
  cyan: 0x72d7ff,
};

const HOT_DAY_BLOCK_SIZE = 5;
const HOT_DAY_BLOCKS = 24;

export function createHeatRenderer() {
  let root = null;
  let staticLayer = null;
  let thermalLayer = null;
  let thermalGraphics = null;
  let maskGraphics = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    thermalLayer = new Container();
    thermalGraphics = new Graphics();
    maskGraphics = new Graphics();
    root.addChild(staticLayer);
    root.addChild(thermalLayer);
    thermalLayer.addChild(thermalGraphics);
    // Rising shimmer strokes can drift; a hard rect mask keeps the scene
    // inside the instrument frame (same pattern as no2.js).
    thermalLayer.mask = maskGraphics;
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root || !thermalGraphics) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    thermalGraphics.clear();
    drawThermalDisplay(thermalGraphics, bounds, theme, visualState, now, resolveVariant(theme));
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawThermalFrame(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.1 });
    const frame = innerFrame(bounds);
    maskGraphics.clear();
    maskGraphics.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: 0xffffff });
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(thermalLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    thermalLayer = null;
    thermalGraphics = null;
    maskGraphics = null;
  }

  return { init, update, resize, destroy };
}

function drawThermalFrame(container, bounds, theme) {
  const g = new Graphics();
  const frame = innerFrame(bounds);
  g.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: theme.lcd, alpha: 0.84 });
  g.rect(frame.x, frame.y, frame.w, frame.h).stroke({ width: 2, color: theme.line, alpha: 0.78 });
  g.rect(frame.x + 9, frame.y + 9, frame.w - 18, frame.h - 18)
    .stroke({ width: 1, color: theme.lineSoft, alpha: 0.55 });
  container.addChild(g);
}

function drawThermalDisplay(g, bounds, theme, visualState, now, variant) {
  const scene = getUrbanSceneRect(bounds);
  const intensity = clamp01(visualState.intensity || 0);

  if (!isMeasuredValue(visualState.displayValue)) {
    drawUnavailableState(g, scene, theme);
    return;
  }

  if (variant === "thermal_magnitude") {
    drawMagnitudeScene(g, scene, theme, intensity, now);
    return;
  }
  if (variant === "hot_day_register") {
    drawHotDayRegister(g, scene, theme, visualState, intensity, now);
    return;
  }
  if (variant === "night_retention") {
    drawNightScene(g, scene, theme, intensity, now);
    return;
  }
  if (variant === "wildfire_smoke") {
    drawWildfireScene(g, scene, theme, intensity, now);
    return;
  }
  drawCompositeScene(g, scene, theme, intensity, now);
}

function resolveVariant(theme) {
  if (theme?.variant) return theme.variant;
  const id = theme?.id || "heat_index";
  if (id === "heat_summer_tmax") return "thermal_magnitude";
  if (id === "heat_hot_days") return "hot_day_register";
  if (id === "heat_tropical_nights") return "night_retention";
  return "thermal_burden";
}

// --- Scene 1: Tmax magnitude — how hard the sun hits ---------------------
function drawMagnitudeScene(g, scene, theme, intensity, now) {
  drawDaySky(g, scene, theme, intensity);
  drawThermalSkyline(g, scene, theme, { intensity });
  const sunX = scene.x + scene.w * 0.74;
  const sunY = scene.y + scene.h * 0.24;
  const sunR = scene.w * (0.045 + intensity * 0.03);
  drawSunDisc(g, scene, theme, { x: sunX, y: sunY, radius: sunR, intensity, active: true, now });
  drawRadiantGlow(g, scene, theme, { intensity, now });
  drawConvectionShimmer(g, scene, theme, { intensity, now, speed: 2200, xFrom: 0.04, xTo: 0.98 });
  drawHorizontalThermometer(g, scene, theme, { intensity, xFrom: 0.08, xTo: 0.92 });
}

// --- Scene 2: hot-day frequency — an annual threshold register -----------
// Each illuminated segment is five days with Tmax >= 30 °C. This is a count
// register, deliberately not a calendar: the source does not identify which
// dates were hot or whether they were consecutive.
function drawHotDayRegister(g, scene, theme, visualState, intensity, now) {
  const accent = theme.particle || theme.accent;
  const blocks = segmentedCount(visualState.displayValue, {
    blockSize: HOT_DAY_BLOCK_SIZE,
    maxBlocks: HOT_DAY_BLOCKS,
  });
  const cols = 6;
  const rows = HOT_DAY_BLOCKS / cols;
  const gap = Math.max(2, scene.w * 0.012);
  const cellW = (scene.w * 0.68 - gap * (cols - 1)) / cols;
  const cellH = Math.max(5, scene.h * 0.09);
  const x0 = scene.x + scene.w * 0.16;
  const y0 = scene.y + scene.h * 0.23;

  drawDaySky(g, scene, theme, intensity * 0.55);
  drawThermalSkyline(g, scene, theme, { intensity: intensity * 0.3 });
  const sunX = scene.x + scene.w * 0.83;
  const sunY = scene.y + scene.h * 0.2;
  drawSunDisc(g, scene, theme, { x: sunX, y: sunY, radius: scene.w * 0.03, intensity, active: true, now });

  for (let i = 0; i < HOT_DAY_BLOCKS; i += 1) {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = x0 + col * (cellW + gap);
    const y = y0 + row * (cellH + gap);
    const active = i < blocks;
    const pulse = active ? 0.84 + Math.sin(now / 600 + i * 0.7) * 0.16 : 1;
    g.roundRect(x, y, cellW, cellH, 1.5).fill({
      color: active ? accent : theme.lineSoft,
      alpha: active ? (0.38 + intensity * 0.38) * pulse : 0.26,
    });
    g.roundRect(x, y, cellW, cellH, 1.5).stroke({ width: 1, color: theme.line, alpha: active ? 0.45 : 0.22 });
  }
  const railY = y0 + rows * (cellH + gap) + scene.h * 0.035;
  g.moveTo(x0, railY).lineTo(x0 + scene.w * 0.68, railY).stroke({ width: 1, color: accent, alpha: 0.48 });
  drawConvectionShimmer(g, scene, theme, {
    intensity: intensity * 0.55,
    now,
    speed: 2600,
    alpha: 0.55,
    xFrom: 0.22,
    xTo: 0.78,
    baseY: railY,
    rise: scene.h * (0.1 + intensity * 0.12),
  });
}

// --- Scene 3: tropical nights — the city can't cool down ------------------
function drawNightScene(g, scene, theme, intensity, now) {
  drawNightSky(g, scene);
  drawStars(g, scene, theme, { count: 16, now });
  const moonX = scene.x + scene.w * 0.78;
  const moonY = scene.y + scene.h * 0.22;
  drawMoon(g, scene, theme, { x: moonX, y: moonY, radius: scene.w * 0.04 });
  drawThermalSkyline(g, scene, theme, { intensity, night: true });
  drawRadiantGlow(g, scene, theme, { intensity, now });
  drawConvectionShimmer(g, scene, theme, { intensity, now, speed: 4200, alpha: 0.8, xFrom: 0.06, xTo: 0.96 });
  drawWarmWindows(g, scene, theme, { intensity, now });
}

// --- Scene 4: composite index — no relief day or night --------------------
function drawCompositeScene(g, scene, theme, intensity, now) {
  // Left half: day.
  drawDaySky(g, scene, theme, intensity, { xFrom: 0, xTo: 0.5 });
  drawThermalSkyline(g, scene, theme, { intensity, xFrom: 0.02, xTo: 0.5 });
  const sunX = scene.x + scene.w * 0.24;
  const sunY = scene.y + scene.h * 0.22;
  drawSunDisc(g, scene, theme, { x: sunX, y: sunY, radius: scene.w * (0.035 + intensity * 0.02), intensity, active: true, now });
  drawRadiantGlow(g, scene, theme, { intensity, now, xFrom: 0.02, xTo: 0.48 });
  drawConvectionShimmer(g, scene, theme, { intensity, now, speed: 2200, xFrom: 0.04, xTo: 0.48 });
  drawHorizontalThermometer(g, scene, theme, { intensity, xFrom: 0.06, xTo: 0.44 });

  // Right half: night.
  drawNightSky(g, scene, { xFrom: 0.5, xTo: 1 });
  drawStars(g, scene, theme, { count: 8, now });
  const moonX = scene.x + scene.w * 0.76;
  const moonY = scene.y + scene.h * 0.22;
  drawMoon(g, scene, theme, { x: moonX, y: moonY, radius: scene.w * 0.032 });
  drawThermalSkyline(g, scene, theme, { intensity, night: true, xFrom: 0.5, xTo: 0.98 });
  drawRadiantGlow(g, scene, theme, { intensity, now, xFrom: 0.5, xTo: 0.98 });
  drawConvectionShimmer(g, scene, theme, { intensity: intensity * 0.8, now, speed: 4200, alpha: 0.7, xFrom: 0.52, xTo: 0.96 });
  drawWarmWindows(g, scene, theme, { intensity, now, xFrom: 0.5, xTo: 0.98 });

  drawTwilightDivider(g, scene, theme);
}

// --- Scene 5: wildfire exposure — smoke on the horizon --------------------
// The city itself is unchanged (same fixed skyline as the other scenes);
// only the haze and the plumes rising behind it react to intensity.
function drawWildfireScene(g, scene, theme, intensity, now) {
  drawDaySky(g, scene, theme, intensity);
  drawSmokePlumes(g, scene, theme, intensity, now);
  drawThermalSkyline(g, scene, theme, { intensity });
  // Amber haze over the sky, deepening with more smoke.
  g.rect(scene.x, scene.y, scene.w, scene.h * 0.72)
    .fill({ color: 0xd9a441, alpha: 0.04 + intensity * 0.22 });
  const sunX = scene.x + scene.w * 0.72;
  const sunY = scene.y + scene.h * 0.2;
  drawSunDisc(g, scene, theme, {
    x: sunX,
    y: sunY,
    radius: scene.w * 0.045,
    intensity: intensity * 0.3,
    active: true,
    now,
  });
}

function drawSmokePlumes(g, scene, theme, intensity, now) {
  const groundY = getGroundY(scene);
  const plumes = [0.14, 0.32, 0.58].map((x, i) => ({
    x: scene.x + scene.w * x,
    seed: seeded(i * 5.3),
  }));
  for (const plume of plumes) {
    const drift = Math.sin(now / 2600 + plume.seed * 6) * scene.w * 0.02;
    const height = scene.h * (0.1 + intensity * 0.42) * (0.7 + plume.seed * 0.6);
    const puffs = 4;
    for (let i = 0; i < puffs; i += 1) {
      const t = i / (puffs - 1);
      const y = groundY - height * t;
      const x = plume.x + drift * t;
      const r = scene.w * (0.02 + t * 0.035) * (0.5 + intensity * 0.6);
      g.circle(x, y, r).fill({ color: 0x8ca4bf, alpha: (0.05 + intensity * 0.22) * (1 - t * 0.4) });
    }
  }
}

// --- Shared sky ------------------------------------------------------------
function drawDaySky(g, scene, theme, intensity, { xFrom = 0, xTo = 1 } = {}) {
  const warm = theme.particle || theme.accent;
  const span = xTo - xFrom;
  g.rect(scene.x + scene.w * xFrom, scene.y, scene.w * span, scene.h * 0.72)
    .fill({ color: COLORS.panel, alpha: 0.5 });
  // Warm wash toward the top that deepens with intensity.
  g.rect(scene.x + scene.w * xFrom, scene.y, scene.w * span, scene.h * 0.4)
    .fill({ color: warm, alpha: 0.03 + intensity * 0.08 });
}

function drawNightSky(g, scene, { xFrom = 0, xTo = 1 } = {}) {
  const span = xTo - xFrom;
  g.rect(scene.x + scene.w * xFrom, scene.y, scene.w * span, scene.h * 0.72)
    .fill({ color: COLORS.deepNight, alpha: 0.74 });
}

function innerFrame(bounds) {
  return {
    x: bounds.width * 0.08,
    y: bounds.height * 0.13,
    w: bounds.width * 0.84,
    h: bounds.height * 0.68,
  };
}

function sameBounds(a, b) {
  return b && a.width === b.width && a.height === b.height;
}

function destroyChildren(container) {
  if (!container) return;
  for (const child of container.removeChildren()) {
    try { child.destroy({ children: true }); } catch (_) {}
  }
}
