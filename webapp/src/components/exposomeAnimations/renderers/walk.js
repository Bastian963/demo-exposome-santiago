import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";

// Street corner: sidewalk, crosswalk and storefronts are fixed; only the
// pedestrians crossing and the lit storefront windows react to intensity
// (walk_index — higher = more walkable = a livelier corner).
export function createWalkRenderer() {
  let root = null;
  let staticLayer = null;
  let dynamicLayer = null;
  let lastBounds = null;

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
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    destroyChildren(dynamicLayer);
    const t = clamp01(visualState.intensity ?? 0);
    drawWalkScene(dynamicLayer, getScene(bounds), theme, t, now);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawFrame(staticLayer, bounds, theme);
    drawStreetBase(staticLayer, getScene(bounds), theme);
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
  }

  return { init, update, resize, destroy };
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

// Fixed geometry: sidewalk, street, crosswalk stripes, 4 storefronts.
function drawStreetBase(container, scene, theme) {
  const g = new Graphics();
  const roadY = scene.y + scene.h * 0.72;
  const roadH = scene.h * 0.16;
  g.rect(scene.x, roadY, scene.w, roadH).fill({ color: theme.lineSoft, alpha: 0.5 });
  const stripeW = scene.w * 0.05;
  for (let i = 0; i < 6; i += 1) {
    const x = scene.x + scene.w * 0.4 + i * stripeW * 1.4;
    g.rect(x, roadY + roadH * 0.15, stripeW, roadH * 0.7).fill({ color: theme.white, alpha: 0.5 });
  }
  g.rect(scene.x, scene.y + scene.h * 0.6, scene.w, scene.h * 0.12).fill({ color: theme.lineSoft, alpha: 0.28 });

  const buildings = [
    { x: 0.04, w: 0.16, h: 0.5 },
    { x: 0.24, w: 0.14, h: 0.42 },
    { x: 0.62, w: 0.15, h: 0.46 },
    { x: 0.8, w: 0.16, h: 0.52 },
  ];
  for (const b of buildings) {
    const bx = scene.x + scene.w * b.x;
    const bw = scene.w * b.w;
    const bh = scene.h * b.h;
    const by = scene.y + scene.h * 0.6 - bh;
    g.rect(bx, by, bw, bh).fill({ color: 0x101425, alpha: 0.75 });
    g.rect(bx, by, bw, bh).stroke({ width: 1, color: theme.line, alpha: 0.35 });
  }
  container.addChild(g);
}

function drawWalkScene(container, scene, theme, t, now) {
  const g = new Graphics();
  const roadY = scene.y + scene.h * 0.72;
  const accent = theme.particle || theme.accent;

  // Storefront windows: more lit as walkability rises.
  const buildings = [
    { x: 0.04, w: 0.16, h: 0.5, windows: 3 },
    { x: 0.24, w: 0.14, h: 0.42, windows: 2 },
    { x: 0.62, w: 0.15, h: 0.46, windows: 2 },
    { x: 0.8, w: 0.16, h: 0.52, windows: 3 },
  ];
  let winIndex = 0;
  for (const b of buildings) {
    const bx = scene.x + scene.w * b.x;
    const bw = scene.w * b.w;
    const bh = scene.h * b.h;
    const by = scene.y + scene.h * 0.6 - bh;
    for (let i = 0; i < b.windows; i += 1) {
      const lit = seeded(winIndex * 3.1) < 0.25 + t * 0.7;
      winIndex += 1;
      const wx = bx + bw * (0.2 + i * 0.32);
      const wy = by + bh * 0.28;
      g.rect(wx, wy, bw * 0.18, bw * 0.18).fill({ color: lit ? accent : theme.lineSoft, alpha: lit ? 0.75 : 0.25 });
    }
  }

  // Pedestrians crossing: count scales with t; each walks the crosswalk
  // width on a loop timed by its own seed so they don't move in lockstep.
  const count = Math.round(1 + t * 6);
  for (let i = 0; i < count; i += 1) {
    const seed = seeded(i * 7.7);
    const period = 3200 + seed * 1400;
    const phase = ((now + seed * period) % period) / period;
    const px = scene.x + scene.w * (0.4 + phase * 0.34);
    const py = roadY + scene.h * 0.16 * (0.2 + seed * 0.6);
    g.circle(px, py - 6, 2.6).fill({ color: theme.white, alpha: 0.8 });
    g.rect(px - 2, py - 3, 4, 8).fill({ color: accent, alpha: 0.85 });
  }
  container.addChild(g);
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
