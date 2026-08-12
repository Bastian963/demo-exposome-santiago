import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";

export function createSocialRenderer() {
  let root = null;
  let staticLayer = null;
  let dynamicLayer = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    dynamicLayer = new Container();
    root.addChild(staticLayer);
    root.addChild(dynamicLayer);
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    destroyChildren(dynamicLayer);
    const t = clamp01(visualState.intensity ?? 0);
    if (theme?.variant === "social_assets") {
      drawSocialInfrastructureMonitor(dynamicLayer, bounds, theme, t, now);
    } else if (theme?.variant === "healthcare_access") {
      drawHealthcareAccessMonitor(dynamicLayer, bounds, theme, t, now);
    } else {
      drawSocioeconomicMonitor(dynamicLayer, bounds, theme, t, now);
    }
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawFrame(staticLayer, bounds, theme);
    drawGrid(staticLayer, bounds, theme);
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

function drawFrame(container, bounds, theme) {
  const g = new Graphics();
  const box = getBox(bounds);
  g.roundRect(box.x, box.y, box.w, box.h, 8).fill({ color: theme.lcd, alpha: 0.88 });
  g.roundRect(box.x, box.y, box.w, box.h, 8).stroke({ width: 2, color: theme.line, alpha: 0.75 });
  g.roundRect(box.x + 8, box.y + 8, box.w - 16, box.h - 16, 5)
    .stroke({ width: 1, color: theme.lineSoft, alpha: 0.72 });
  container.addChild(g);
}

function drawGrid(container, bounds, theme) {
  const g = new Graphics();
  const box = getBox(bounds);
  const left = box.x + 20;
  const right = box.x + box.w - 20;
  const top = box.y + 20;
  const bottom = box.y + box.h - 24;
  for (let i = 1; i < 5; i += 1) {
    const y = top + (bottom - top) * (i / 5);
    g.moveTo(left, y).lineTo(right, y).stroke({ width: 1, color: theme.grid, alpha: 0.45 });
  }
  g.moveTo(left, top + (bottom - top) * 0.5)
    .lineTo(right, top + (bottom - top) * 0.5)
    .stroke({ width: 2, color: theme.white, alpha: 0.22 });
  container.addChild(g);
}

function drawSocioeconomicMonitor(container, bounds, theme, t, now) {
  const box = getBox(bounds);
  const left = box.x + 28;
  const right = box.x + box.w - 28;
  const top = box.y + 28;
  const bottom = box.y + box.h - 34;
  const width = right - left;
  const height = bottom - top;
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.004);
  const levelY = bottom - height * t;

  drawDeprivationFloor(container, { left, right, top, bottom, height }, theme, t, pulse);
  drawStrataBars(container, { left, top, bottom, width, height }, theme, t, pulse);
  drawMedianLine(container, { left, right, top, bottom, height }, theme);
  drawPositionMarker(container, { left, right, levelY }, theme, t, pulse);
}

function drawSocialInfrastructureMonitor(container, bounds, theme, t, now) {
  const box = getBox(bounds);
  const scene = {
    x: box.x + 16,
    y: box.y + 16,
    w: box.w - 32,
    h: box.h - 28,
  };
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.0045);
  const nodes = infrastructureNodes(scene);
  drawDistrictBase(container, scene, theme, t);
  drawAccessNetwork(container, nodes, theme, t, pulse);
  drawInfrastructureNodes(container, nodes, theme, t, pulse);
  drawCapacityMeter(container, scene, theme, t, pulse);
}

function drawDistrictBase(container, scene, theme, t) {
  const g = new Graphics();
  g.rect(scene.x, scene.y, scene.w, scene.h).fill({ color: 0x0c1422, alpha: 0.5 });
  const road = theme.lineSoft;
  const roadAlpha = 0.24 + t * 0.18;
  const cx = scene.x + scene.w * 0.5;
  const cy = scene.y + scene.h * 0.56;
  g.rect(scene.x + scene.w * 0.08, cy - 4, scene.w * 0.84, 8).fill({ color: road, alpha: roadAlpha });
  g.rect(cx - 4, scene.y + scene.h * 0.16, 8, scene.h * 0.72).fill({ color: road, alpha: roadAlpha });
  for (let i = 0; i < 4; i += 1) {
    const x = scene.x + scene.w * (0.16 + i * 0.2);
    g.moveTo(x, cy).lineTo(x + scene.w * 0.07, cy).stroke({ width: 1, color: theme.line, alpha: 0.22 });
  }
  g.rect(scene.x + scene.w * 0.08, scene.y + scene.h * 0.72, scene.w * 0.22, scene.h * 0.12)
    .fill({ color: 0x2e7d4f, alpha: 0.12 + t * 0.16 });
  container.addChild(g);
}

function infrastructureNodes(scene) {
  return [
    { key: "park", x: 0.18, y: 0.76, threshold: 0.08 },
    { key: "community", x: 0.28, y: 0.28, threshold: 0.24 },
    { key: "library", x: 0.5, y: 0.4, threshold: 0.42 },
    { key: "sport", x: 0.71, y: 0.7, threshold: 0.58 },
    { key: "health", x: 0.78, y: 0.24, threshold: 0.74 },
  ].map((n) => ({
    ...n,
    px: scene.x + scene.w * n.x,
    py: scene.y + scene.h * n.y,
    size: Math.max(10, scene.w * 0.075),
  }));
}

function drawAccessNetwork(container, nodes, theme, t, pulse) {
  const g = new Graphics();
  const activeColor = theme.particle || theme.accent;
  for (let i = 0; i < nodes.length - 1; i += 1) {
    const a = nodes[i];
    const b = nodes[i + 1];
    const active = clamp01((t - Math.max(a.threshold, b.threshold) + 0.18) / 0.32);
    g.moveTo(a.px, a.py)
      .lineTo(b.px, b.py)
      .stroke({
        width: 1 + active * 1.5,
        color: active > 0.2 ? activeColor : theme.lineSoft,
        alpha: 0.12 + active * (0.36 + pulse * 0.12),
      });
  }
  container.addChild(g);
}

function drawInfrastructureNodes(container, nodes, theme, t, pulse) {
  const g = new Graphics();
  for (const node of nodes) {
    const active = clamp01((t - node.threshold + 0.22) / 0.34);
    const color = active > 0.15 ? theme.particle || theme.accent : theme.line;
    const glow = 0.06 + active * (0.16 + pulse * 0.08);
    g.circle(node.px, node.py, node.size * (1.25 + active * 0.35)).fill({ color, alpha: glow });
    drawNodeBase(g, node, theme, active);
    if (node.key === "park") drawParkNode(g, node, theme, active);
    if (node.key === "community") drawCommunityNode(g, node, theme, active);
    if (node.key === "library") drawLibraryNode(g, node, theme, active);
    if (node.key === "sport") drawSportNode(g, node, theme, active);
    if (node.key === "health") drawHealthNode(g, node, theme, active);
  }
  container.addChild(g);
}

function drawNodeBase(g, node, theme, active) {
  const s = node.size;
  g.roundRect(node.px - s, node.py - s, s * 2, s * 2, 4)
    .fill({ color: 0x101425, alpha: 0.7 });
  g.roundRect(node.px - s, node.py - s, s * 2, s * 2, 4)
    .stroke({ width: 1, color: active > 0.15 ? theme.particle || theme.accent : theme.line, alpha: 0.32 + active * 0.42 });
}

function drawParkNode(g, node, theme, active) {
  const s = node.size;
  const green = active > 0.2 ? 0x73eff7 : theme.lcdMuted;
  g.rect(node.px - s * 0.08, node.py - s * 0.1, s * 0.16, s * 0.7).fill({ color: 0xf4b41b, alpha: 0.35 + active * 0.35 });
  g.circle(node.px, node.py - s * 0.25, s * 0.48).fill({ color: green, alpha: 0.22 + active * 0.55 });
  g.circle(node.px - s * 0.34, node.py - s * 0.08, s * 0.32).fill({ color: green, alpha: 0.18 + active * 0.42 });
  g.circle(node.px + s * 0.34, node.py - s * 0.08, s * 0.32).fill({ color: green, alpha: 0.18 + active * 0.42 });
}

function drawCommunityNode(g, node, theme, active) {
  const s = node.size;
  g.rect(node.px - s * 0.55, node.py - s * 0.25, s * 1.1, s * 0.72)
    .fill({ color: theme.lineSoft, alpha: 0.38 + active * 0.28 });
  g.moveTo(node.px - s * 0.68, node.py - s * 0.25)
    .lineTo(node.px, node.py - s * 0.72)
    .lineTo(node.px + s * 0.68, node.py - s * 0.25)
    .stroke({ width: 1, color: theme.line, alpha: 0.52 + active * 0.25 });
  for (let i = -1; i <= 1; i += 1) {
    g.circle(node.px + i * s * 0.32, node.py + s * 0.08, s * 0.11).fill({ color: theme.white, alpha: 0.35 + active * 0.45 });
  }
}

function drawLibraryNode(g, node, theme, active) {
  const s = node.size;
  g.rect(node.px - s * 0.62, node.py - s * 0.48, s * 1.24, s * 0.2)
    .fill({ color: theme.particle || theme.accent, alpha: 0.2 + active * 0.46 });
  g.rect(node.px - s * 0.54, node.py + s * 0.34, s * 1.08, s * 0.12)
    .fill({ color: theme.line, alpha: 0.4 + active * 0.2 });
  for (let i = -1; i <= 1; i += 1) {
    g.rect(node.px + i * s * 0.32 - s * 0.06, node.py - s * 0.24, s * 0.12, s * 0.58)
      .fill({ color: theme.white, alpha: 0.32 + active * 0.42 });
  }
}

function drawSportNode(g, node, theme, active) {
  const s = node.size;
  g.rect(node.px - s * 0.64, node.py - s * 0.38, s * 1.28, s * 0.76)
    .stroke({ width: 1, color: theme.white, alpha: 0.24 + active * 0.48 });
  g.moveTo(node.px, node.py - s * 0.36).lineTo(node.px, node.py + s * 0.36)
    .stroke({ width: 1, color: theme.white, alpha: 0.18 + active * 0.35 });
  g.circle(node.px, node.py, s * 0.18).stroke({ width: 1, color: theme.particle || theme.accent, alpha: 0.22 + active * 0.48 });
}

function drawHealthNode(g, node, theme, active) {
  const s = node.size;
  g.rect(node.px - s * 0.52, node.py - s * 0.48, s * 1.04, s * 0.96)
    .fill({ color: theme.lineSoft, alpha: 0.38 + active * 0.25 });
  const color = active > 0.25 ? 0xff77a8 : theme.lcdMuted;
  g.rect(node.px - s * 0.1, node.py - s * 0.36, s * 0.2, s * 0.72).fill({ color, alpha: 0.32 + active * 0.55 });
  g.rect(node.px - s * 0.36, node.py - s * 0.1, s * 0.72, s * 0.2).fill({ color, alpha: 0.32 + active * 0.55 });
}

function drawCapacityMeter(container, scene, theme, t, pulse) {
  const g = new Graphics();
  const x = scene.x + scene.w * 0.18;
  const y = scene.y + scene.h * 0.91;
  const w = scene.w * 0.64;
  const h = Math.max(5, scene.h * 0.035);
  g.roundRect(x, y, w, h, h / 2).stroke({ width: 1, color: theme.line, alpha: 0.42 });
  g.roundRect(x + 1, y + 1, Math.max(2, w * t - 2), h - 2, (h - 2) / 2)
    .fill({ color: theme.particle || theme.accent, alpha: 0.42 + t * 0.34 + pulse * 0.06 });
  container.addChild(g);
}

// Healthcare access: a clinic at the center of a fixed neighborhood grid
// (reuses the district base from the infrastructure scene) with houses at
// fixed, seeded positions. `t` is distance-derived (higher = farther), so
// coverage = 1 - t: the ring around the clinic — and the count of houses
// it reaches — shrinks as the nearest facility gets farther away. Only the
// ring radius and each house's lit/unlit state are dynamic; the grid,
// clinic, and house positions never move.
function drawHealthcareAccessMonitor(container, bounds, theme, t, now) {
  const box = getBox(bounds);
  const scene = { x: box.x + 16, y: box.y + 16, w: box.w - 32, h: box.h - 28 };
  const coverage = 1 - t;
  const cx = scene.x + scene.w * 0.5;
  const cy = scene.y + scene.h * 0.52;
  const maxRadius = Math.min(scene.w, scene.h) * 0.42;
  const radius = maxRadius * (0.18 + coverage * 0.82);
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.004);

  drawDistrictBase(container, scene, theme, coverage);

  const g = new Graphics();
  const accent = theme.particle || theme.accent;
  g.circle(cx, cy, radius).fill({ color: accent, alpha: 0.06 + coverage * 0.1 });
  g.circle(cx, cy, radius).stroke({ width: 1.5, color: accent, alpha: 0.3 + coverage * 0.4 + pulse * 0.08 });

  const s = Math.max(10, scene.w * 0.06);
  g.roundRect(cx - s, cy - s, s * 2, s * 2, 4).fill({ color: 0x101425, alpha: 0.85 });
  g.roundRect(cx - s, cy - s, s * 2, s * 2, 4).stroke({ width: 1, color: accent, alpha: 0.6 });
  const cross = 0xff77a8;
  g.rect(cx - s * 0.12, cy - s * 0.55, s * 0.24, s * 1.1).fill({ color: cross, alpha: 0.75 });
  g.rect(cx - s * 0.55, cy - s * 0.12, s * 1.1, s * 0.24).fill({ color: cross, alpha: 0.75 });

  for (const house of healthcareHouses(scene, cx, cy)) {
    const reached = house.dist <= radius;
    g.roundRect(house.x - 3, house.y - 3, 6, 6, 1)
      .fill({ color: reached ? accent : theme.line, alpha: reached ? 0.5 + pulse * 0.15 : 0.14 });
  }
  container.addChild(g);
}

function healthcareHouses(scene, cx, cy) {
  const n = 10;
  const houses = [];
  for (let i = 0; i < n; i += 1) {
    const angle = (i / n) * Math.PI * 2 + seededHouse(i) * 0.6;
    const r = Math.min(scene.w, scene.h) * (0.12 + seededHouse(i + 50) * 0.4);
    houses.push({ x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r * 0.7, dist: r });
  }
  return houses;
}

function seededHouse(i) {
  const x = Math.sin(i * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function drawDeprivationFloor(container, area, theme, t, pulse) {
  const g = new Graphics();
  const pressure = 1 - t;
  const h = area.height * (0.1 + pressure * 0.58);
  const y = area.bottom - h;
  g.roundRect(area.left, y, area.right - area.left, h, 5)
    .fill({ color: 0xff004d, alpha: 0.1 + pressure * 0.22 });
  for (let i = 0; i < 5; i += 1) {
    const yy = area.bottom - h * ((i + 1) / 6);
    g.moveTo(area.left + 8, yy)
      .lineTo(area.right - 8, yy + Math.sin(i + pulse) * 2)
      .stroke({ width: 1, color: 0xff77a8, alpha: 0.16 + pressure * 0.16 });
  }
  container.addChild(g);
}

function drawStrataBars(container, area, theme, t, pulse) {
  const g = new Graphics();
  const n = 6;
  const gap = 8;
  const barW = (area.width - gap * (n - 1)) / n;
  for (let i = 0; i < n; i += 1) {
    const x = area.left + i * (barW + gap);
    const threshold = i / (n - 1);
    const active = clamp01((t - threshold * 0.74) / 0.34);
    const baseH = area.height * (0.18 + i * 0.055);
    const extraH = area.height * (0.38 * active);
    const h = baseH + extraH;
    const y = area.bottom - h;
    const color = active > 0.6 ? theme.accent : i < 2 ? 0xff77a8 : 0xf4b41b;
    g.roundRect(x, y, barW, h, 4).fill({ color, alpha: 0.2 + active * 0.58 });
    g.roundRect(x, y, barW, h, 4).stroke({ width: 1, color: theme.white, alpha: 0.18 + active * 0.32 });
    const nodeY = y - 7 - active * 6 + pulse * active * 2;
    g.circle(x + barW / 2, nodeY, 3.2 + active * 2.5)
      .fill({ color, alpha: 0.35 + active * 0.5 });
  }
  container.addChild(g);
}

function drawMedianLine(container, area, theme) {
  const g = new Graphics();
  const y = area.top + area.height * 0.5;
  g.moveTo(area.left, y)
    .lineTo(area.right, y)
    .stroke({ width: 1, color: theme.white, alpha: 0.38 });
  container.addChild(g);
}

function drawPositionMarker(container, area, theme, t, pulse) {
  const g = new Graphics();
  const x = area.left + (area.right - area.left) * 0.5;
  const radius = 8 + pulse * 2;
  const color = t < 0.38 ? 0xff77a8 : t > 0.68 ? theme.accent : 0xf4b41b;
  g.moveTo(area.left - 4, area.levelY)
    .lineTo(area.right + 4, area.levelY)
    .stroke({ width: 2, color, alpha: 0.55 });
  g.circle(x, area.levelY, radius).fill({ color, alpha: 0.28 });
  g.circle(x, area.levelY, 4).fill({ color: theme.white, alpha: 0.88 });
  container.addChild(g);
}

function getBox(bounds) {
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
