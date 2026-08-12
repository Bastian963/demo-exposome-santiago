import { Graphics } from "pixi.js";
import { getUrbanSceneRect } from "./pixelCity.js";

// NO2 is a combustion gas: the monitor reads as a street with cars
// trailing exhaust, so more traffic = more gas, instead of an abstract
// haze that doesn't explain where the pollutant comes from.
export function getTrafficFrame(bounds) {
  return getUrbanSceneRect(bounds);
}

export function drawPixelTraffic({ container, bounds, theme, intensity = 0, now = 0 }) {
  const scene = getUrbanSceneRect(bounds);
  const g = new Graphics();
  const roadTop = scene.y + scene.h * 0.6;
  const roadH = scene.h * 0.24;
  const roadBottom = roadTop + roadH;

  drawFactories(g, scene, theme, roadTop);
  drawChimneySmoke(g, scene, theme, intensity, now, roadTop);
  drawHaze(g, scene, theme, intensity, roadTop);
  drawRoad(g, scene, theme, roadTop, roadH, roadBottom);

  const carCount = Math.min(6, 1 + Math.round(intensity * 5));
  drawCars(g, scene, theme, intensity, now, roadTop, roadH, carCount);

  container.addChild(g);
  return g;
}

// Background industry: factory silhouettes with smokestacks sit behind the
// road, since NO2 comes from vehicular AND industrial combustion. Buildings
// are always visible; the number of actively-smoking chimneys scales with
// intensity, same pattern as carCount below.
const FACTORIES = [
  { x: 0.03, w: 0.14, h: 0.3, chimneys: [{ x: 0.25, h: 0.22 }, { x: 0.75, h: 0.16 }] },
  { x: 0.21, w: 0.09, h: 0.2, chimneys: [{ x: 0.5, h: 0.18 }] },
  { x: 0.56, w: 0.16, h: 0.28, chimneys: [{ x: 0.2, h: 0.2 }, { x: 0.6, h: 0.24 }, { x: 0.85, h: 0.15 }] },
  { x: 0.79, w: 0.12, h: 0.18, chimneys: [{ x: 0.5, h: 0.16 }] },
];

function drawFactories(g, scene, theme, roadTop) {
  for (const f of FACTORIES) {
    const x = scene.x + scene.w * f.x;
    const w = scene.w * f.w;
    const h = scene.h * f.h;
    const y = roadTop - h;
    g.rect(x, y, w, h).fill({ color: theme.lineSoft, alpha: 0.3 });
    g.rect(x, y, w, h).stroke({ width: 1, color: theme.line, alpha: 0.36 });

    for (const c of f.chimneys) {
      const chimneyW = Math.max(3, w * 0.09);
      const chimneyH = scene.h * c.h;
      const chimneyX = x + w * c.x - chimneyW / 2;
      const chimneyY = y - chimneyH;
      g.rect(chimneyX, chimneyY, chimneyW, chimneyH).fill({ color: theme.lineSoft, alpha: 0.4 });
      g.rect(chimneyX, chimneyY, chimneyW, chimneyH).stroke({ width: 1, color: theme.line, alpha: 0.4 });
    }
  }
}

function drawChimneySmoke(g, scene, theme, intensity, now, roadTop) {
  const chimneyTops = [];
  for (const f of FACTORIES) {
    const x = scene.x + scene.w * f.x;
    const w = scene.w * f.w;
    const h = scene.h * f.h;
    const y = roadTop - h;
    for (const c of f.chimneys) {
      const chimneyW = Math.max(3, w * 0.09);
      const chimneyX = x + w * c.x;
      const chimneyY = y - scene.h * c.h;
      chimneyTops.push({ x: chimneyX, y: chimneyY, w: chimneyW });
    }
  }
  if (chimneyTops.length === 0) return;

  const activeChimneys = Math.min(
    chimneyTops.length,
    1 + Math.round(intensity * (chimneyTops.length - 1))
  );
  const color = theme.particle || theme.accent;
  const puffs = 5;

  for (let i = 0; i < activeChimneys; i++) {
    const top = chimneyTops[i];
    const seed = i * 53.7;
    for (let k = 0; k < puffs; k++) {
      const rise = scene.h * (0.045 + intensity * 0.05);
      const cycle = (now / 2600 + seed + k / puffs) % 1;
      const wobble = Math.sin(now / 900 + seed + k * 1.3) * (top.w * 0.6 + k * 1.2);
      const px = top.x + wobble;
      const py = top.y - cycle * rise * puffs;
      const size = top.w * (0.55 + cycle * 1.3) * (0.7 + intensity * 0.6);
      const alpha = Math.max(0, (0.32 - cycle * 0.28) * (0.4 + intensity * 0.85));
      g.circle(px, py, size).fill({ color, alpha });
    }
  }
}

function drawHaze(g, scene, theme, intensity, roadTop) {
  if (intensity <= 0.02) return;
  const color = theme.particle || theme.accent;
  const layers = 3;
  for (let i = 0; i < layers; i++) {
    const h = scene.h * (0.05 + i * 0.035);
    const y = Math.max(scene.y, roadTop - h * (i + 1) * 0.7);
    const alpha = (0.05 + intensity * 0.17) * (1 - i * 0.3);
    g.rect(scene.x, y, scene.w, h).fill({ color, alpha });
  }
}

function drawRoad(g, scene, theme, roadTop, roadH, roadBottom) {
  g.rect(scene.x, roadTop, scene.w, roadH).fill({ color: theme.lineSoft, alpha: 0.34 });
  g.moveTo(scene.x + scene.w * 0.03, roadBottom).lineTo(scene.x + scene.w * 0.97, roadBottom);
  g.moveTo(scene.x + scene.w * 0.03, roadTop).lineTo(scene.x + scene.w * 0.97, roadTop);
  g.stroke({ width: 1, color: theme.line, alpha: 0.42 });

  const dashY = roadTop + roadH * 0.5;
  const dashW = scene.w * 0.035;
  const gap = scene.w * 0.03;
  for (let x = scene.x + scene.w * 0.05; x < scene.x + scene.w * 0.95; x += dashW + gap) {
    g.rect(x, dashY - 1, dashW, 2).fill({ color: theme.line, alpha: 0.5 });
  }
}

function drawCars(g, scene, theme, intensity, now, roadTop, roadH, carCount) {
  const carW = Math.max(14, scene.w * 0.1);
  const carH = Math.max(7, roadH * 0.36);
  const speed = 34 + intensity * 30; // px/s
  const travel = scene.w + carW * 2;

  for (let i = 0; i < carCount; i++) {
    const lane = i % 2;
    const dir = lane === 0 ? 1 : -1;
    const laneY = roadTop + roadH * (lane === 0 ? 0.28 : 0.72) - carH / 2;
    const seed = i * 71.3;
    const phase = ((seed % travel) + travel) % travel;
    const t = ((now / 1000) * speed + phase) % travel;
    const x = dir > 0 ? scene.x - carW + t : scene.x + scene.w + carW - t;

    if (x + carW < scene.x || x > scene.x + scene.w) continue;
    drawExhaust(g, x, laneY, carW, carH, dir, theme, intensity, now, i);
    drawCarBody(g, x, laneY, carW, carH, theme, dir, i);
  }
}

function drawExhaust(g, x, y, carW, carH, dir, theme, intensity, now, index) {
  if (intensity <= 0.02) return;
  const color = theme.particle || theme.accent;
  const tailX = dir > 0 ? x : x + carW;
  const puffs = 4;
  for (let k = 0; k < puffs; k++) {
    const spread = 6 + intensity * 5;
    const wobble = Math.sin(now / 260 + index * 2.1 + k) * 1.6;
    const px = tailX - dir * (k * spread + 4) + wobble;
    const py = y + carH * 0.55 - k * (2.2 + intensity * 1.6);
    const size = 2 + k * 0.9 + intensity * 1.4;
    const alpha = Math.max(0, (0.4 - k * 0.09) * (0.35 + intensity * 0.85));
    g.circle(px, py, size).fill({ color, alpha });
  }
}

function drawCarBody(g, x, y, w, h, theme, dir, index) {
  const bodyColor = theme.lcdMuted || theme.line;
  g.rect(x, y, w, h).fill({ color: bodyColor, alpha: 0.9 });
  g.rect(x, y, w, h).stroke({ width: 1, color: theme.line, alpha: 0.6 });

  const cabinW = w * 0.5;
  const cabinX = dir > 0 ? x + w * 0.28 : x + w * 0.22;
  g.rect(cabinX, y - h * 0.35, cabinW, h * 0.4).fill({ color: theme.lineSoft, alpha: 0.85 });

  const wheelR = Math.max(1.2, h * 0.22);
  g.circle(x + w * 0.24, y + h, wheelR).fill({ color: theme.grid, alpha: 0.95 });
  g.circle(x + w * 0.76, y + h, wheelR).fill({ color: theme.grid, alpha: 0.95 });

  const lightX = dir > 0 ? x + w - 2 : x + 2;
  g.rect(lightX - 1, y + h * 0.3, 2, h * 0.3).fill({ color: theme.accent, alpha: 0.5 + 0.15 * (index % 2) });
}
