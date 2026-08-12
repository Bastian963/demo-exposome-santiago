import { Graphics } from "pixi.js";

const BUILDINGS = [
  { x: 0.05, w: 0.11, h: 0.38, floors: 5 },
  { x: 0.17, w: 0.13, h: 0.52, floors: 7 },
  { x: 0.31, w: 0.09, h: 0.32, floors: 4 },
  { x: 0.42, w: 0.15, h: 0.58, floors: 8 },
  { x: 0.59, w: 0.1, h: 0.43, floors: 6 },
  { x: 0.71, w: 0.12, h: 0.49, floors: 7 },
  { x: 0.85, w: 0.1, h: 0.34, floors: 5 },
];

const LAMPS = [
  { x: 0.2, h: 0.28 },
  { x: 0.5, h: 0.33 },
  { x: 0.78, h: 0.26 },
];

export function getUrbanSceneRect(bounds) {
  return {
    x: bounds.width * 0.08,
    y: bounds.height * 0.13,
    w: bounds.width * 0.84,
    h: bounds.height * 0.68,
  };
}

export function drawPixelCity({ container, bounds, theme, intensity = 0, now = 0 }) {
  const scene = getUrbanSceneRect(bounds);
  const g = new Graphics();
  const groundY = scene.y + scene.h * 0.74;
  const groundH = Math.max(8, scene.h * 0.08);

  g.rect(scene.x, groundY, scene.w, groundH)
    .fill({ color: theme.lineSoft, alpha: 0.24 + intensity * 0.05 });
  g.moveTo(scene.x + scene.w * 0.03, groundY)
    .lineTo(scene.x + scene.w * 0.97, groundY);
  g.stroke({ width: 1, color: theme.line, alpha: 0.42 });

  drawBuildings(g, scene, theme, intensity, now, groundY);
  drawStreetlights(g, scene, theme, intensity, now, groundY);

  container.addChild(g);
  return g;
}

export function getLampSources(bounds) {
  const scene = getUrbanSceneRect(bounds);
  const groundY = scene.y + scene.h * 0.74;
  return LAMPS.map((lamp) => ({
    x: scene.x + scene.w * lamp.x,
    y: groundY - scene.h * lamp.h,
    groundY,
  }));
}

function drawBuildings(g, scene, theme, intensity, now, groundY) {
  for (let i = 0; i < BUILDINGS.length; i++) {
    const b = BUILDINGS[i];
    const x = scene.x + scene.w * b.x;
    const w = scene.w * b.w;
    const h = scene.h * b.h;
    const y = groundY - h;
    g.rect(x, y, w, h).fill({ color: theme.lineSoft, alpha: 0.34 });
    g.rect(x, y, w, h).stroke({ width: 1, color: theme.line, alpha: 0.34 });
    drawWindows(g, x, y, w, h, b.floors, theme, intensity, now, i);
  }
}

function drawWindows(g, x, y, w, h, floors, theme, intensity, now, buildingIndex) {
  const cols = Math.max(2, Math.floor(w / 18));
  const winW = Math.max(3, Math.floor(w / (cols * 2.2)));
  const winH = Math.max(3, Math.floor(h / (floors * 3.4)));
  const xGap = (w - cols * winW) / (cols + 1);
  const yGap = (h - floors * winH) / (floors + 1);

  for (let r = 0; r < floors; r++) {
    for (let c = 0; c < cols; c++) {
      const seed = buildingIndex * 37 + r * 11 + c * 5;
      const activity = seeded(seed);
      const pulse = Math.sin(now / 2400 + seed * 0.71) * 0.035;
      const active = activity < intensity * 1.18 + 0.08;
      const alpha = active
        ? Math.max(0.1, 0.22 + intensity * 0.48 + pulse)
        : 0.02 + intensity * 0.04;
      g.rect(x + xGap + c * (winW + xGap), y + yGap + r * (winH + yGap), winW, winH)
        .fill({ color: theme.accent, alpha });
    }
  }
}

function drawStreetlights(g, scene, theme, intensity, now, groundY) {
  for (let i = 0; i < LAMPS.length; i++) {
    const lamp = LAMPS[i];
    const x = scene.x + scene.w * lamp.x;
    const topY = groundY - scene.h * lamp.h;
    const pulse = Math.sin(now / 2600 + i * 1.7) * 0.04;
    const lampAlpha = 0.36 + intensity * 0.48 + pulse;

    g.moveTo(x, groundY).lineTo(x, topY);
    g.stroke({ width: 2, color: theme.line, alpha: 0.42 });
    g.rect(x - 7, topY - 3, 14, 4).fill({ color: theme.line, alpha: 0.36 });
    g.rect(x - 4, topY - 1, 8, 5).fill({ color: theme.accent, alpha: lampAlpha });
    g.rect(x - 3, groundY, 6, 3).fill({ color: theme.line, alpha: 0.34 });
  }
}

function seeded(seed) {
  return Math.abs(Math.sin(seed * 12.9898) * 43758.5453) % 1;
}
