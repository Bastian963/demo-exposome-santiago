import { Container, Graphics } from "pixi.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { clamp01 } from "../transitions.js";
import { isMeasuredValue, percentageCellCount, segmentedCount } from "../monitorSemantics.js";
import { drawUnavailableState } from "../primitives/monitorState.js";
import {
  drawThermalSkyline,
  drawSunDisc,
} from "../primitives/pixelThermalCity.js";
import {
  getUrbanSceneRect,
  drawClouds,
  drawRainStreaks,
  drawPuddles,
  drawFloodBand,
  drawCrackedGround,
  drawWaterTank,
  drawLightning,
} from "../primitives/pixelRainscape.js";

const COLORS = {
  panel: 0x0c1422,
  stormSky: 0x101a30,
  drySky: 0x14203a,
};

export function createRainRenderer() {
  let root = null;
  let staticLayer = null;
  let rainLayer = null;
  let rainGraphics = null;
  let maskGraphics = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    rainLayer = new Container();
    rainGraphics = new Graphics();
    maskGraphics = new Graphics();
    root.addChild(staticLayer);
    root.addChild(rainLayer);
    rainLayer.addChild(rainGraphics);
    // Rain streaks cycle past the frame edges; hard rect mask keeps the
    // scene inside the instrument bezel (same pattern as no2/heat).
    rainLayer.mask = maskGraphics;
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root || !rainGraphics) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    rainGraphics.clear();
    drawRainDisplay(rainGraphics, bounds, theme, visualState, now);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawRainFrame(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.1 });
    const frame = innerFrame(bounds);
    maskGraphics.clear();
    maskGraphics.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: 0xffffff });
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(rainLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    rainLayer = null;
    rainGraphics = null;
    maskGraphics = null;
  }

  return { init, update, resize, destroy };
}

function drawRainFrame(container, bounds, theme) {
  const g = new Graphics();
  const frame = innerFrame(bounds);
  g.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: theme.lcd, alpha: 0.84 });
  g.rect(frame.x, frame.y, frame.w, frame.h).stroke({ width: 2, color: theme.line, alpha: 0.78 });
  g.rect(frame.x + 9, frame.y + 9, frame.w - 18, frame.h - 18)
    .stroke({ width: 1, color: theme.lineSoft, alpha: 0.55 });
  container.addChild(g);
}

function drawRainDisplay(g, bounds, theme, visualState, now) {
  const scene = getUrbanSceneRect(bounds);
  const intensity = clamp01(visualState.intensity || 0);
  const variant = resolveVariant(theme);

  if (!isMeasuredValue(visualState.displayValue)) {
    drawUnavailableState(g, scene, theme);
    return;
  }

  if (variant === "rain_volume") {
    drawVolumeScene(g, scene, theme, intensity, now);
    return;
  }
  if (variant === "consecutive_dry_run") {
    drawDryRunRegister(g, scene, theme, visualState, intensity, now);
    return;
  }
  if (variant === "drought_frequency") {
    drawDroughtFrequency(g, scene, theme, visualState, intensity, now);
    return;
  }
  if (variant === "storm") {
    drawStormScene(g, scene, theme, intensity, now);
    return;
  }
  drawExtremesScene(g, scene, theme, intensity, now);
}

function resolveVariant(theme) {
  if (theme?.variant) return theme.variant;
  const id = theme?.id || "rain_index";
  if (id === "rain_annual") return "rain_volume";
  if (id === "rain_dry_spell") return "consecutive_dry_run";
  if (id === "precipitation_spi") return "drought_frequency";
  if (id === "rain_heavy") return "storm";
  return "hydro_extremes";
}

// --- Scene 1: annual volume — how much water falls in a year --------------
function drawVolumeScene(g, scene, theme, intensity, now) {
  drawSky(g, scene, COLORS.panel, { });
  drawClouds(g, scene, theme, { now });
  drawThermalSkyline(g, scene, theme, { intensity: 0.3 });
  drawRainStreaks(g, scene, theme, { intensity, now, xFrom: 0.04, xTo: 0.96 });
  drawPuddles(g, scene, theme, { intensity, now, xFrom: 0.04, xTo: 0.96 });
}

// --- Scene 2: dry spell — contiguous maximum-run register -----------------
// The CHIRPS metric is the year's longest uninterrupted dry run. The tape
// therefore records continuity, not an atmospheric impression of dryness.
function drawDryRunRegister(g, scene, theme, visualState, intensity, now) {
  const accent = theme.particle || 0xd9a441;
  const blocks = segmentedCount(visualState.displayValue, { blockSize: 5, maxBlocks: 24 });
  const x0 = scene.x + scene.w * 0.1;
  const y = scene.y + scene.h * 0.48;
  const w = scene.w * 0.8;
  const h = Math.max(11, scene.h * 0.13);
  const gap = Math.max(1.5, scene.w * 0.008);
  const blockW = (w - gap * 23) / 24;

  drawSky(g, scene, COLORS.drySky, {});
  g.rect(x0 - 2, y - 2, w + 4, h + 4).stroke({ width: 1, color: theme.line, alpha: 0.48 });
  for (let i = 0; i < 24; i += 1) {
    const active = i < blocks;
    const pulse = active ? 0.84 + Math.sin(now / 700 + i * 0.45) * 0.16 : 1;
    const x = x0 + i * (blockW + gap);
    g.rect(x, y, blockW, h).fill({
      color: active ? accent : theme.lineSoft,
      alpha: active ? (0.38 + intensity * 0.38) * pulse : 0.28,
    });
  }
  // Blue drop markers only define the start/end of the illustrative run;
  // they do not claim dates of individual rainfall events.
  drawResetDrop(g, x0 - scene.w * 0.035, y + h * 0.5, 0x41a6f6, 0.75);
  drawResetDrop(g, x0 + Math.max(1, blocks) * (blockW + gap) + scene.w * 0.018, y + h * 0.5, 0x41a6f6, blocks ? 0.65 : 0.2);
  const lineY = y + h + scene.h * 0.11;
  g.moveTo(x0, lineY).lineTo(x0 + w, lineY).stroke({ width: 1, color: accent, alpha: 0.35 + intensity * 0.3 });
  for (let i = 0; i <= 6; i += 1) {
    const tx = x0 + w * (i / 6);
    g.moveTo(tx, lineY - 3).lineTo(tx, lineY + 3).stroke({ width: 1, color: theme.line, alpha: 0.38 });
  }
}

function drawResetDrop(g, x, y, color, alpha) {
  g.circle(x, y + 2, 3.5).fill({ color, alpha });
  g.moveTo(x, y - 5).lineTo(x - 3, y).lineTo(x + 3, y).closePath().fill({ color, alpha });
}

// --- Scene 3: SPI drought — percentage of the full observation period -----
// The layer supplies only a percentage, not a month-by-month chronology. The
// scattered 100-cell field is therefore a frequency display, never a calendar.
function drawDroughtFrequency(g, scene, theme, visualState, intensity, now) {
  const accent = theme.particle || 0xf4b41b;
  const cells = percentageCellCount(visualState.displayValue, 100);
  const cols = 10;
  const rows = 10;
  const gap = Math.max(1.5, scene.w * 0.008);
  const cellW = (scene.w * 0.72 - gap * (cols - 1)) / cols;
  const cellH = (scene.h * 0.52 - gap * (rows - 1)) / rows;
  const x0 = scene.x + scene.w * 0.14;
  const y0 = scene.y + scene.h * 0.2;

  drawSky(g, scene, COLORS.panel, {});
  for (let i = 0; i < 100; i += 1) {
    const mapped = (i * 37) % 100;
    const active = i < cells;
    const col = mapped % cols;
    const row = Math.floor(mapped / cols);
    const x = x0 + col * (cellW + gap);
    const y = y0 + row * (cellH + gap);
    const pulse = active ? 0.84 + Math.sin(now / 800 + mapped * 0.23) * 0.16 : 1;
    g.rect(x, y, cellW, cellH).fill({
      color: active ? accent : theme.lineSoft,
      alpha: active ? (0.38 + intensity * 0.4) * pulse : 0.25,
    });
  }
  const thresholdY = y0 + scene.h * 0.61;
  g.moveTo(x0, thresholdY).lineTo(x0 + scene.w * 0.72, thresholdY)
    .stroke({ width: 1, color: accent, alpha: 0.5 });
  g.rect(x0, thresholdY + 5, scene.w * 0.72 * intensity, 3)
    .fill({ color: accent, alpha: 0.28 + intensity * 0.28 });
}

// --- Scene 3: storm — dense rain, lightning, flooding ----------------------
function drawStormScene(g, scene, theme, intensity, now) {
  drawSky(g, scene, COLORS.stormSky, {});
  drawClouds(g, scene, theme, { dark: true, now });
  drawThermalSkyline(g, scene, theme, { intensity: 0.3, night: true });
  drawLightning(g, scene, theme, { intensity, now });
  drawRainStreaks(g, scene, theme, { intensity: 0.3 + intensity * 0.7, now, slant: 0.34, speed: 620, xFrom: 0.04, xTo: 0.96 });
  drawFloodBand(g, scene, theme, { intensity, now, xFrom: 0.03, xTo: 0.97 });
}

// --- Scene 4: hydro extremes — storm and drought share the commune ---------
function drawExtremesScene(g, scene, theme, intensity, now) {
  // Left half: storm.
  drawSky(g, scene, COLORS.stormSky, { xFrom: 0, xTo: 0.5 });
  drawClouds(g, scene, theme, { dark: true, now, xFrom: 0.02, xTo: 0.5 });
  drawThermalSkyline(g, scene, theme, { intensity: 0.3, night: true, xFrom: 0.02, xTo: 0.5 });
  drawLightning(g, scene, theme, { intensity, now, xFrom: 0.02, xTo: 0.48 });
  drawRainStreaks(g, scene, theme, { intensity: 0.25 + intensity * 0.75, now, slant: 0.34, speed: 620, xFrom: 0.04, xTo: 0.48 });
  drawFloodBand(g, scene, theme, { intensity, now, xFrom: 0.03, xTo: 0.48 });

  // Right half: drought. Amber palette regardless of the index's blue
  // particle color, so the dry story reads like the dry_spell scene.
  const dryTheme = { ...theme, particle: 0xd9a441 };
  drawSky(g, scene, COLORS.drySky, { xFrom: 0.5, xTo: 1 });
  const sunX = scene.x + scene.w * 0.85;
  const sunY = scene.y + scene.h * 0.2;
  drawSunDisc(g, scene, dryTheme, { x: sunX, y: sunY, radius: scene.w * 0.03, intensity: 0.3 + intensity * 0.5, active: true, now });
  drawThermalSkyline(g, scene, dryTheme, { intensity: 0.25, xFrom: 0.52, xTo: 0.98 });
  drawCrackedGround(g, scene, dryTheme, { intensity, xFrom: 0.52, xTo: 0.98 });
  drawWaterTank(g, scene, dryTheme, { intensity, now, x: 0.55 });

  // Divider: rain-to-dry gradient line.
  const x = scene.x + scene.w * 0.5;
  g.rect(x - 1, scene.y + scene.h * 0.04, 1, scene.h * 0.9).fill({ color: 0x41a6f6, alpha: 0.12 });
  g.rect(x, scene.y + scene.h * 0.04, 1, scene.h * 0.9).fill({ color: 0xd9a441, alpha: 0.1 });
}

function drawSky(g, scene, color, { xFrom = 0, xTo = 1 } = {}) {
  const span = xTo - xFrom;
  g.rect(scene.x + scene.w * xFrom, scene.y, scene.w * span, scene.h * 0.72)
    .fill({ color, alpha: 0.6 });
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
