import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";
import { isMeasuredValue, parkAccessState, percentageCellCount } from "../monitorSemantics.js";
import { drawUnavailableState } from "../primitives/monitorState.js";

// Three measurements, three territorial readings: Dynamic World coverage is
// an overhead land-cover mosaic; Meta canopy is shade from crowns >=3 m; OSM
// access is a straight-line distance instrument. They share a family, not a
// metaphor.
export function createGreenRenderer() {
  let root = null;
  let staticLayer = null;
  let dynamicLayer = null;
  let lastBounds = null;
  let lastVariant = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    dynamicLayer = new Container();
    root.addChild(staticLayer, dynamicLayer);
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    const variant = resolveVariant(theme);
    if (!sameBounds(bounds, lastBounds) || variant !== lastVariant) resize(bounds, theme);
    destroyChildren(dynamicLayer);
    const scene = getScene(bounds);
    const g = new Graphics();
    if (!isMeasuredValue(visualState.displayValue)) {
      drawUnavailableState(g, scene, theme);
    } else if (variant === "land_cover") {
      drawLandCover(g, scene, theme, visualState, now);
    } else if (variant === "tree_canopy") {
      drawTreeCanopy(g, scene, theme, visualState, now);
    } else {
      drawParkAccess(g, scene, theme, visualState, now);
    }
    dynamicLayer.addChild(g);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    lastVariant = resolveVariant(theme);
    destroyChildren(staticLayer);
    drawFrame(staticLayer, bounds, theme);
    const scene = getScene(bounds);
    if (lastVariant === "land_cover") drawLandCoverBase(staticLayer, scene, theme);
    else if (lastVariant === "tree_canopy") drawCanopyBase(staticLayer, scene, theme);
    else drawAccessBase(staticLayer, scene, theme);
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(dynamicLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    dynamicLayer = null;
    lastBounds = null;
    lastVariant = null;
  }

  return { init, update, resize, destroy };
}

function resolveVariant(theme) {
  if (theme?.variant) return theme.variant;
  if (theme?.id === "green") return "land_cover";
  if (theme?.id === "canopy") return "tree_canopy";
  return "park_distance";
}

function getScene(bounds) {
  return { x: bounds.width * 0.08, y: bounds.height * 0.13, w: bounds.width * 0.84, h: bounds.height * 0.68 };
}

function drawFrame(container, bounds, theme) {
  const g = new Graphics();
  const scene = getScene(bounds);
  g.rect(scene.x, scene.y, scene.w, scene.h).fill({ color: theme.lcd, alpha: 0.84 });
  g.rect(scene.x, scene.y, scene.w, scene.h).stroke({ width: 2, color: theme.line, alpha: 0.78 });
  container.addChild(g);
}

function drawLandCoverBase(container, scene, theme) {
  const g = new Graphics();
  // Thin road and parcel lines make this a plan view, never a park path.
  for (const ratio of [0.18, 0.47, 0.76]) {
    const x = scene.x + scene.w * ratio;
    g.rect(x - 1, scene.y + scene.h * 0.04, 2, scene.h * 0.92).fill({ color: theme.lineSoft, alpha: 0.58 });
  }
  for (const ratio of [0.27, 0.61]) {
    const y = scene.y + scene.h * ratio;
    g.rect(scene.x + scene.w * 0.04, y - 1, scene.w * 0.92, 2).fill({ color: theme.lineSoft, alpha: 0.58 });
  }
  container.addChild(g);
}

function drawCanopyBase(container, scene, theme) {
  const g = new Graphics();
  const roadY = scene.y + scene.h * 0.65;
  g.rect(scene.x, roadY, scene.w, scene.h * 0.2).fill({ color: theme.lineSoft, alpha: 0.38 });
  g.rect(scene.x, roadY, scene.w, 2).fill({ color: theme.line, alpha: 0.5 });
  for (const side of [0.06, 0.7]) {
    g.rect(scene.x + scene.w * side, scene.y + scene.h * 0.28, scene.w * 0.22, scene.h * 0.37)
      .fill({ color: 0x101425, alpha: 0.56 })
      .stroke({ width: 1, color: theme.line, alpha: 0.3 });
  }
  container.addChild(g);
}

function drawAccessBase(container, scene, theme) {
  const g = new Graphics();
  const horizonY = scene.y + scene.h * 0.32;
  const groundY = scene.y + scene.h * 0.84;
  g.moveTo(scene.x + scene.w * 0.08, groundY)
    .lineTo(scene.x + scene.w * 0.45, horizonY)
    .lineTo(scene.x + scene.w * 0.55, horizonY)
    .lineTo(scene.x + scene.w * 0.92, groundY)
    .fill({ color: theme.lineSoft, alpha: 0.34 });
  g.moveTo(scene.x + scene.w * 0.08, groundY).lineTo(scene.x + scene.w * 0.45, horizonY)
    .stroke({ width: 1, color: theme.line, alpha: 0.36 });
  g.moveTo(scene.x + scene.w * 0.92, groundY).lineTo(scene.x + scene.w * 0.55, horizonY)
    .stroke({ width: 1, color: theme.line, alpha: 0.36 });
  container.addChild(g);
}

function drawLandCover(g, scene, theme, visualState, now) {
  const active = percentageCellCount(visualState.displayValue, 100);
  const intensity = clamp01(visualState.intensity ?? 0);
  const cols = 10;
  const gap = Math.max(1, scene.w * 0.006);
  const cellW = (scene.w * 0.82 - gap * 9) / 10;
  const cellH = (scene.h * 0.78 - gap * 9) / 10;
  const x0 = scene.x + scene.w * 0.09;
  const y0 = scene.y + scene.h * 0.1;
  const palette = [theme.particle || 0x78d6aa, 0xa0e426, 0x5f9e5b];
  for (let i = 0; i < 100; i += 1) {
    const mapped = (i * 47) % 100;
    const col = mapped % cols;
    const row = Math.floor(mapped / cols);
    const x = x0 + col * (cellW + gap);
    const y = y0 + row * (cellH + gap);
    const covered = i < active;
    const pulse = covered ? 0.9 + Math.sin(now / 1000 + mapped * 0.34) * 0.1 : 1;
    g.rect(x, y, cellW, cellH).fill({
      color: covered ? palette[mapped % palette.length] : theme.lineSoft,
      alpha: covered ? (0.4 + intensity * 0.32) * pulse : 0.24,
    });
  }
}

function drawTreeCanopy(g, scene, theme, visualState, now) {
  const coverage = percentageCellCount(visualState.displayValue, 100) / 100;
  const intensity = clamp01(visualState.intensity ?? 0);
  const green = theme.particle || 0x78d6aa;
  const roadY = scene.y + scene.h * 0.65;
  const crowns = 14;
  for (let i = 0; i < crowns; i += 1) {
    const seed = seeded(i * 5.7);
    if (seed > coverage) continue;
    const side = i % 2 === 0 ? 0.16 + seed * 0.24 : 0.6 + seed * 0.22;
    const x = scene.x + scene.w * side;
    const y = roadY - scene.h * (0.04 + seed * 0.13);
    const r = scene.w * (0.028 + coverage * 0.045) * (0.8 + seed * 0.4);
    const sway = Math.sin(now / 1800 + i) * (0.4 + intensity * 1.1);
    g.circle(x + sway, y, r * 1.3).fill({ color: green, alpha: 0.18 + coverage * 0.22 });
    g.circle(x + sway, y, r).fill({ color: green, alpha: 0.3 + coverage * 0.36 });
    g.rect(x - r * 0.1, y + r * 0.5, r * 0.2, scene.h * 0.18).fill({ color: theme.line, alpha: 0.45 });
    g.ellipse(x + sway * 1.7, roadY + scene.h * 0.035, r * 1.5, Math.max(2, r * 0.28))
      .fill({ color: green, alpha: 0.1 + coverage * 0.2 });
  }
  const shadeW = scene.w * 0.72 * coverage;
  g.rect(scene.x + scene.w * 0.14, scene.y + scene.h * 0.88, shadeW, 4)
    .fill({ color: green, alpha: 0.28 + intensity * 0.3 });
}

function drawParkAccess(g, scene, theme, visualState, now) {
  const state = parkAccessState(visualState.displayValue, visualState.intensity);
  const green = theme.particle || 0x78d6aa;
  if (state.status === "no_park_mapped") {
    const cx = scene.x + scene.w * 0.5;
    const cy = scene.y + scene.h * 0.45;
    g.rect(cx - scene.w * 0.12, cy - scene.h * 0.12, scene.w * 0.24, scene.h * 0.24)
      .stroke({ width: 1.5, color: theme.line, alpha: 0.62 });
    g.moveTo(cx - scene.w * 0.09, cy - scene.h * 0.09).lineTo(cx + scene.w * 0.09, cy + scene.h * 0.09)
      .stroke({ width: 2, color: theme.lcdMuted, alpha: 0.75 });
    g.moveTo(cx + scene.w * 0.09, cy - scene.h * 0.09).lineTo(cx - scene.w * 0.09, cy + scene.h * 0.09)
      .stroke({ width: 2, color: theme.lcdMuted, alpha: 0.75 });
    return;
  }
  const t = state.distanceT;
  const horizonY = scene.y + scene.h * (0.32 + t * 0.14);
  const parkScale = 1.05 - t * 0.58;
  const parkX = scene.x + scene.w * 0.5;
  const parkW = scene.w * 0.22 * parkScale;
  const parkH = scene.h * 0.18 * parkScale;
  const segments = 2 + Math.round(t * 8);
  const startY = scene.y + scene.h * 0.82;
  for (let i = 0; i < segments; i += 1) {
    const phase = (i + 0.5) / segments;
    const y = startY + (horizonY - startY) * phase;
    const halfW = scene.w * (0.31 * (1 - phase) + 0.035);
    g.moveTo(parkX - halfW, y).lineTo(parkX + halfW, y)
      .stroke({ width: 1.4, color: theme.lcdMuted, alpha: 0.34 + t * 0.22 });
  }
  const shimmer = 0.9 + Math.sin(now / 1700) * 0.1;
  g.roundRect(parkX - parkW / 2, horizonY - parkH, parkW, parkH, 3)
    .fill({ color: green, alpha: (0.3 + (1 - t) * 0.38) * shimmer });
  for (let i = 0; i < 3; i += 1) {
    const tx = parkX + (i - 1) * parkW * 0.28;
    g.circle(tx, horizonY - parkH, parkH * 0.42).fill({ color: green, alpha: 0.42 + (1 - t) * 0.32 });
  }
}

function seeded(i) {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
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
