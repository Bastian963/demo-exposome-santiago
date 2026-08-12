import { getUrbanSceneRect } from "./pixelCity.js";

// Shared pixel-art vocabulary for the four heat monitors. The heat exposome is
// an URBAN heat story, so every scene reuses the same city box and silhouette
// language as NO2/ALAN, then layers a physical mechanism on top (sun, shimmer,
// re-radiation, scorched ground) instead of abstract spectrum bars.

export { getUrbanSceneRect };

// Own skyline layout (distinct from pixelCity's LAMPS scene): a denser row of
// low-rise blocks so the ground band reads as "urban fabric" that soaks up and
// re-radiates heat.
const THERMAL_BUILDINGS = [
  { x: 0.04, w: 0.1, h: 0.3 },
  { x: 0.15, w: 0.12, h: 0.44 },
  { x: 0.28, w: 0.08, h: 0.26 },
  { x: 0.37, w: 0.13, h: 0.5 },
  { x: 0.51, w: 0.09, h: 0.34 },
  { x: 0.61, w: 0.11, h: 0.46 },
  { x: 0.73, w: 0.08, h: 0.28 },
  { x: 0.82, w: 0.12, h: 0.4 },
];

export function getGroundY(scene) {
  return scene.y + scene.h * 0.72;
}

// The scene box, minus a small inset so nothing paints over the bezel.
export function getSceneInterior(bounds) {
  const scene = getUrbanSceneRect(bounds);
  return {
    x: scene.x + scene.w * 0.02,
    y: scene.y + scene.h * 0.04,
    w: scene.w * 0.96,
    h: scene.h * 0.92,
  };
}

export function drawThermalSkyline(g, scene, theme, { intensity = 0, night = false, xFrom = 0, xTo = 1 } = {}) {
  const groundY = getGroundY(scene);
  const groundH = Math.max(8, scene.h * 0.1);
  const span = xTo - xFrom;

  // Ground band.
  g.rect(scene.x + scene.w * xFrom, groundY, scene.w * span, groundH)
    .fill({ color: theme.lineSoft, alpha: night ? 0.2 : 0.26 + intensity * 0.05 });
  g.moveTo(scene.x + scene.w * (xFrom + 0.01), groundY)
    .lineTo(scene.x + scene.w * (xTo - 0.01), groundY);
  g.stroke({ width: 1, color: theme.line, alpha: 0.4 });

  for (const b of THERMAL_BUILDINGS) {
    if (b.x < xFrom || b.x + b.w > xTo) continue;
    const x = scene.x + scene.w * b.x;
    const w = scene.w * b.w;
    const h = scene.h * b.h;
    const y = groundY - h;
    g.rect(x, y, w, h).fill({ color: theme.lineSoft, alpha: night ? 0.3 : 0.32 });
    g.rect(x, y, w, h).stroke({ width: 1, color: theme.line, alpha: 0.32 });
  }
}

// Returns the buildings visible within [xFrom, xTo] so callers can attach
// radiant glow or windows to real silhouettes.
export function getThermalBuildings(scene, { xFrom = 0, xTo = 1 } = {}) {
  const groundY = getGroundY(scene);
  return THERMAL_BUILDINGS.filter((b) => b.x >= xFrom && b.x + b.w <= xTo).map((b) => {
    const w = scene.w * b.w;
    const h = scene.h * b.h;
    const x = scene.x + scene.w * b.x;
    return { x, y: groundY - h, w, h, groundY };
  });
}

export function drawSunDisc(g, scene, theme, { x, y, radius, intensity = 0, active = true, now = 0 } = {}) {
  const color = theme.particle || theme.accent;
  if (!active) {
    // Outline-only "spent" sun for the frequency arc.
    g.circle(x, y, radius).stroke({ width: 1, color, alpha: 0.22 });
    return;
  }
  // Halo grows with intensity.
  const haloR = radius * (1.8 + intensity * 1.4);
  const pulse = 0.9 + Math.sin(now / 1400) * 0.1;
  g.circle(x, y, haloR).fill({ color, alpha: (0.05 + intensity * 0.12) * pulse });
  g.circle(x, y, radius * (1.3 + intensity * 0.5)).fill({ color, alpha: 0.1 + intensity * 0.16 });
  g.circle(x, y, radius).fill({ color, alpha: 0.55 + intensity * 0.4 });
  // Pixel rays.
  const rays = 8;
  const rayLen = radius * (0.6 + intensity * 0.9);
  for (let i = 0; i < rays; i++) {
    const a = (i / rays) * Math.PI * 2 + now / 5200;
    const r0 = radius * 1.25;
    const r1 = radius * 1.25 + rayLen;
    g.moveTo(x + Math.cos(a) * r0, y + Math.sin(a) * r0)
      .lineTo(x + Math.cos(a) * r1, y + Math.sin(a) * r1);
  }
  g.stroke({ width: 1, color, alpha: 0.2 + intensity * 0.35 });
}

export function drawMoon(g, scene, theme, { x, y, radius } = {}) {
  const cool = theme.white || 0xe6eef7;
  g.circle(x, y, radius * 2.1).fill({ color: cool, alpha: 0.05 });
  g.circle(x, y, radius).fill({ color: cool, alpha: 0.5 });
  // Crescent shadow.
  g.circle(x + radius * 0.5, y - radius * 0.25, radius * 0.92)
    .fill({ color: theme.lcd, alpha: 0.6 });
}

export function drawStars(g, scene, theme, { count = 14, now = 0 } = {}) {
  const cool = theme.white || 0xe6eef7;
  for (let i = 0; i < count; i++) {
    const sx = scene.x + scene.w * (0.1 + seeded(i * 7.3) * 0.8);
    const sy = scene.y + scene.h * (0.08 + seeded(i * 3.1) * 0.34);
    const twinkle = 0.3 + (Math.sin(now / 900 + i * 1.7) + 1) * 0.25;
    g.rect(sx, sy, 1.5, 1.5).fill({ color: cool, alpha: twinkle });
  }
}

// Rising heat-haze: short vertical wavering strokes climbing from the ground,
// borrowing drawChimneySmoke's cycle+wobble mechanic but as translucent warm
// distortion rather than smoke puffs. This is the honest replacement for the
// old horizontal OP-1 bands.
export function drawConvectionShimmer(g, scene, theme, { intensity = 0, now = 0, speed = 2400, alpha = 1, xFrom = 0, xTo = 1, baseY = null, rise = null } = {}) {
  if (intensity <= 0.02) return;
  const color = theme.particle || theme.accent;
  const groundY = baseY ?? getGroundY(scene);
  const columns = Math.max(4, Math.round(6 + intensity * 8));
  const climb = rise ?? scene.h * (0.2 + intensity * 0.26);
  const span = xTo - xFrom;

  for (let i = 0; i < columns; i++) {
    const t = columns > 1 ? i / (columns - 1) : 0.5;
    const baseX = scene.x + scene.w * (xFrom + 0.05 + t * (span - 0.1));
    const seed = i * 41.3;
    const segments = 6;
    let prevX = baseX;
    let prevY = groundY;
    for (let s = 1; s <= segments; s++) {
      const cycle = ((now / speed + seed + s / segments) % 1);
      const wobble = Math.sin(now / 620 + seed + s * 1.4) * scene.w * (0.009 + intensity * 0.013);
      const px = baseX + wobble;
      const py = groundY - (s / segments) * climb;
      const a = Math.max(0, (0.42 - (s / segments) * 0.3) * (0.45 + intensity * 0.95) * alpha) * (0.6 + cycle * 0.4);
      g.moveTo(prevX, prevY).lineTo(px, py);
      g.stroke({ width: 1.5, color, alpha: a });
      prevX = px;
      prevY = py;
    }
  }
}

// Amber re-radiation glow anchored to the base of walls and the ground: the
// concrete giving back the day's heat at night. Stacked rects with decaying
// alpha (like drawHaze, but bottom-anchored).
export function drawRadiantGlow(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1 } = {}) {
  if (intensity <= 0.01) return;
  const color = theme.particle || theme.accent;
  const groundY = getGroundY(scene);
  const span = xTo - xFrom;
  const layers = 5;
  const pulse = 0.86 + Math.sin(now / 1800) * 0.14;
  for (let i = 0; i < layers; i++) {
    const h = scene.h * (0.045 + i * 0.032);
    const y = groundY - h;
    const a = (0.09 + intensity * 0.22) * (1 - i * 0.19) * pulse;
    g.rect(scene.x + scene.w * xFrom, y, scene.w * span, h).fill({ color, alpha: a });
  }
  // Glow climbing the wall bases.
  for (const b of getThermalBuildings(scene, { xFrom, xTo })) {
    const glowH = b.h * (0.22 + intensity * 0.38);
    g.rect(b.x, b.groundY - glowH, b.w, glowH).fill({ color, alpha: (0.07 + intensity * 0.16) * pulse });
  }
}

// Warm amber windows for the tropical-nights scene: sparse, deliberately
// different from ALAN's cool-white windows. The lit pattern is FIXED (seeded,
// not intensity-gated) so map hover previews never flicker windows on/off;
// the data signal lives in the radiant glow, not here.
export function drawWarmWindows(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1 } = {}) {
  const color = theme.particle || theme.accent;
  const buildings = getThermalBuildings(scene, { xFrom, xTo });
  buildings.forEach((b, bi) => {
    const cols = Math.max(2, Math.floor(b.w / 14));
    const rows = Math.max(3, Math.floor(b.h / 18));
    const winW = Math.max(2, Math.floor(b.w / (cols * 2.4)));
    const winH = Math.max(2, Math.floor(b.h / (rows * 2.8)));
    const xGap = (b.w - cols * winW) / (cols + 1);
    const yGap = (b.h - rows * winH) / (rows + 1);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const seed = bi * 29 + r * 13 + c * 7;
        if (seeded(seed) >= 0.45) continue;
        const pulse = Math.sin(now / 2100 + seed * 0.6) * 0.05;
        const alpha = Math.max(0.12, 0.32 + intensity * 0.14 + pulse);
        g.rect(b.x + xGap + c * (winW + xGap), b.y + yGap + r * (winH + yGap), winW, winH)
          .fill({ color, alpha });
      }
    }
  });
}

// Horizontal thermometer near the ground: a plain rounded tube (no bulb)
// filling left-to-right with intensity, tick marks above.
export function drawHorizontalThermometer(g, scene, theme, { intensity = 0, xFrom = 0.08, xTo = 0.92, y = null } = {}) {
  const color = theme.particle || theme.accent;
  const amber = 0xd9a441;
  const tubeY = y ?? getGroundY(scene) + scene.h * 0.045;
  const x0 = scene.x + scene.w * xFrom;
  const x1 = scene.x + scene.w * xTo;
  const w = x1 - x0;
  const h = Math.max(7, scene.h * 0.045);
  const fillW = Math.max(0, (w - 4) * intensity);
  g.roundRect(x0, tubeY, w, h, h / 2).stroke({ width: 1, color: amber, alpha: 0.48 });
  if (fillW > h / 2) {
    g.roundRect(x0 + 2, tubeY + 2, fillW, h - 4, (h - 4) / 2)
      .fill({ color, alpha: 0.3 + intensity * 0.5 });
  }
  for (let i = 0; i < 5; i++) {
    const tx = x0 + w * (i / 4);
    g.moveTo(tx, tubeY - 3).lineTo(tx, tubeY - 8);
    g.stroke({ width: 1, color: amber, alpha: 0.25 + i * 0.04 });
  }
}

// Vertical twilight divider for the composite day/night scene.
export function drawTwilightDivider(g, scene, theme) {
  const x = scene.x + scene.w * 0.5;
  const warm = theme.particle || theme.accent;
  const cool = theme.white || 0xe6eef7;
  g.rect(x - 1, scene.y + scene.h * 0.04, 1, scene.h * 0.9).fill({ color: warm, alpha: 0.12 });
  g.rect(x, scene.y + scene.h * 0.04, 1, scene.h * 0.9).fill({ color: cool, alpha: 0.08 });
}

export function seeded(seed) {
  return Math.abs(Math.sin(seed * 12.9898) * 43758.5453) % 1;
}
