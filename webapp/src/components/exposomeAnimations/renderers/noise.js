import { Container, Graphics } from "pixi.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { clamp01 } from "../transitions.js";

export function createNoiseRenderer() {
  let root = null;
  let staticLayer = null;
  let noiseLayer = null;
  let noiseGraphics = null;
  let maskGraphics = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    noiseLayer = new Container();
    noiseGraphics = new Graphics();
    maskGraphics = new Graphics();
    root.addChild(staticLayer);
    root.addChild(noiseLayer);
    noiseLayer.addChild(noiseGraphics);
    noiseLayer.mask = maskGraphics;
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root || !noiseGraphics) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    noiseGraphics.clear();
    drawNoiseDisplay(noiseGraphics, bounds, theme, visualState, now);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawNoiseFrame(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.1 });
    const frame = innerFrame(bounds);
    maskGraphics.clear();
    maskGraphics.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: 0xffffff });
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(noiseLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    noiseLayer = null;
    noiseGraphics = null;
    maskGraphics = null;
    lastBounds = null;
  }

  return { init, update, resize, destroy };
}

function drawNoiseFrame(container, bounds, theme) {
  const g = new Graphics();
  const frame = innerFrame(bounds);
  g.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: theme.lcd, alpha: 0.86 });
  g.rect(frame.x, frame.y, frame.w, frame.h).stroke({ width: 2, color: theme.line, alpha: 0.78 });
  g.rect(frame.x + 8, frame.y + 8, frame.w - 16, frame.h - 16)
    .stroke({ width: 1, color: theme.lineSoft, alpha: 0.62 });
  container.addChild(g);
}

function drawNoiseDisplay(g, bounds, theme, visualState, now) {
  const scene = getScene(bounds);
  const intensity = clamp01(visualState.acoustic ?? visualState.intensity ?? 0);
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.006);
  drawBackdrop(g, scene, theme, intensity);
  drawBuildings(g, scene, theme, intensity, pulse);
  drawRoad(g, scene, theme);
  const carCenters = drawCars(g, scene, theme, intensity, now);
  drawSoundWaves(g, scene, theme, intensity, now, carCenters);
  drawNoiseMeter(g, scene, theme, intensity, pulse);
}

function drawBackdrop(g, scene, theme, intensity) {
  g.rect(scene.x, scene.y, scene.w, scene.h * 0.68)
    .fill({ color: 0x101a30, alpha: 0.68 });
  g.rect(scene.x, scene.y + scene.h * 0.58, scene.w, scene.h * 0.42)
    .fill({ color: theme.lineSoft, alpha: 0.22 + intensity * 0.18 });
}

function drawBuildings(g, scene, theme, intensity, pulse) {
  const blocks = [
    { x: 0.04, w: 0.12, h: 0.42 },
    { x: 0.19, w: 0.1, h: 0.34 },
    { x: 0.67, w: 0.11, h: 0.38 },
    { x: 0.82, w: 0.13, h: 0.46 },
  ];
  const baseY = scene.y + scene.h * 0.61;
  for (const b of blocks) {
    const x = scene.x + scene.w * b.x;
    const w = scene.w * b.w;
    const h = scene.h * b.h;
    const y = baseY - h;
    g.rect(x, y, w, h).fill({ color: theme.lineSoft, alpha: 0.34 });
    g.rect(x, y, w, h).stroke({ width: 1, color: theme.line, alpha: 0.32 });
    const cols = 2;
    const rows = 3;
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const wx = x + w * (0.24 + c * 0.34);
        const wy = y + h * (0.22 + r * 0.22);
        g.rect(wx, wy, w * 0.12, h * 0.08)
          .fill({ color: theme.particle || theme.accent, alpha: (0.12 + intensity * 0.14) * (0.7 + pulse * 0.3) });
      }
    }
  }
}

function drawRoad(g, scene, theme) {
  const roadY = scene.y + scene.h * 0.63;
  const roadH = scene.h * 0.25;
  g.rect(scene.x, roadY, scene.w, roadH).fill({ color: 0x151b31, alpha: 0.9 });
  g.moveTo(scene.x + scene.w * 0.04, roadY).lineTo(scene.x + scene.w * 0.96, roadY);
  g.moveTo(scene.x + scene.w * 0.04, roadY + roadH).lineTo(scene.x + scene.w * 0.96, roadY + roadH);
  g.stroke({ width: 1, color: theme.line, alpha: 0.42 });
  const dashY = roadY + roadH * 0.5;
  const dashW = scene.w * 0.04;
  for (let x = scene.x + scene.w * 0.07; x < scene.x + scene.w * 0.94; x += dashW * 1.8) {
    g.rect(x, dashY - 1, dashW, 2).fill({ color: theme.line, alpha: 0.52 });
  }
}

function drawCars(g, scene, theme, intensity, now) {
  const centers = [];
  const roadY = scene.y + scene.h * 0.63;
  const roadH = scene.h * 0.25;
  const count = 2 + Math.round(intensity * 5);
  const carW = Math.max(13, scene.w * 0.095);
  const carH = Math.max(7, roadH * 0.28);
  const travel = scene.w + carW * 2;
  const speed = 22 + intensity * 42;

  for (let i = 0; i < count; i += 1) {
    const lane = i % 2;
    const dir = lane === 0 ? 1 : -1;
    const laneY = roadY + roadH * (lane === 0 ? 0.32 : 0.72) - carH / 2;
    const phase = (i * 61.7) % travel;
    const t = ((now / 1000) * speed + phase) % travel;
    const x = dir > 0 ? scene.x - carW + t : scene.x + scene.w + carW - t;
    if (x + carW < scene.x || x > scene.x + scene.w) continue;
    const color = i % 3 === 0 ? theme.particle || theme.accent : theme.lcdMuted || theme.line;
    g.rect(x, laneY, carW, carH).fill({ color, alpha: 0.82 });
    g.rect(x, laneY, carW, carH).stroke({ width: 1, color: theme.white, alpha: 0.22 });
    const cabinX = dir > 0 ? x + carW * 0.3 : x + carW * 0.2;
    g.rect(cabinX, laneY - carH * 0.32, carW * 0.48, carH * 0.36)
      .fill({ color: theme.lineSoft, alpha: 0.86 });
    g.circle(x + carW * 0.25, laneY + carH, Math.max(1.2, carH * 0.22)).fill({ color: theme.grid, alpha: 0.95 });
    g.circle(x + carW * 0.75, laneY + carH, Math.max(1.2, carH * 0.22)).fill({ color: theme.grid, alpha: 0.95 });
    centers.push({ x: x + carW / 2, y: laneY + carH * 0.5 });
  }
  return centers;
}

function drawSoundWaves(g, scene, theme, intensity, now, carCenters) {
  const color = theme.particle || theme.accent;
  const waveCount = 3 + Math.round(intensity * 4);
  const anchors = carCenters.length ? carCenters : [{ x: scene.x + scene.w * 0.5, y: scene.y + scene.h * 0.69 }];
  for (let i = 0; i < waveCount; i += 1) {
    const anchor = anchors[i % anchors.length];
    const cycle = (now / (950 - intensity * 260) + i * 0.18) % 1;
    const radius = scene.w * (0.04 + cycle * (0.18 + intensity * 0.12));
    const alpha = Math.max(0, (1 - cycle) * (0.1 + intensity * 0.38));
    g.circle(anchor.x, anchor.y, radius).stroke({ width: 1.2 + intensity * 1.4, color, alpha });
  }
  const vibration = 3 + Math.round(intensity * 8);
  for (let i = 0; i < vibration; i += 1) {
    const y = scene.y + scene.h * (0.18 + i * 0.055);
    const wobble = Math.sin(now / 120 + i * 1.8) * intensity * 4;
    g.moveTo(scene.x + scene.w * 0.1, y)
      .lineTo(scene.x + scene.w * 0.22 + wobble, y + wobble * 0.25)
      .stroke({ width: 1, color, alpha: 0.12 + intensity * 0.16 });
    g.moveTo(scene.x + scene.w * 0.78 - wobble, y - wobble * 0.25)
      .lineTo(scene.x + scene.w * 0.9, y)
      .stroke({ width: 1, color, alpha: 0.12 + intensity * 0.16 });
  }
}

function drawNoiseMeter(g, scene, theme, intensity, pulse) {
  const x = scene.x + scene.w * 0.38;
  const y = scene.y + scene.h * 0.08;
  const w = scene.w * 0.24;
  const h = Math.max(7, scene.h * 0.045);
  const fillW = Math.max(2, w * intensity);
  g.roundRect(x, y, w, h, h / 2).stroke({ width: 1, color: theme.line, alpha: 0.54 });
  g.roundRect(x + 2, y + 2, Math.max(2, fillW - 4), h - 4, (h - 4) / 2)
    .fill({ color: theme.particle || theme.accent, alpha: 0.5 + intensity * 0.35 + pulse * 0.08 });
}

function innerFrame(bounds) {
  return {
    x: bounds.width * 0.08,
    y: bounds.height * 0.13,
    w: bounds.width * 0.84,
    h: bounds.height * 0.68,
  };
}

function getScene(bounds) {
  return {
    x: bounds.width * 0.11,
    y: bounds.height * 0.16,
    w: bounds.width * 0.78,
    h: bounds.height * 0.58,
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
