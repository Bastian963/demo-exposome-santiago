import { getUrbanSceneRect, getGroundY, seeded } from "./pixelThermalCity.js";

// Shared pixel-art vocabulary for the four rain monitors. Same rule as the
// thermal scenes: fixed props (clouds, sky, tank shell, sun) never depend on
// intensity — the data signal lives in how much water falls, pools, cracks
// or drains.

export { getUrbanSceneRect, getGroundY };

const RAIN_COLORS = {
  cloud: 0x94b0c2,
  cloudDark: 0x4a5f7d,
  water: 0x41a6f6,
  waterLight: 0x73eff7,
  lightning: 0xf4f4f4,
};

// Puffy pixel clouds along the top of the scene. Always drawn (fixed prop);
// `dark` switches to the storm nimbus look.
export function drawClouds(g, scene, theme, { dark = false, now = 0, xFrom = 0, xTo = 1 } = {}) {
  const color = dark ? RAIN_COLORS.cloudDark : RAIN_COLORS.cloud;
  const span = xTo - xFrom;
  const count = Math.max(2, Math.round(3 * span));
  for (let i = 0; i < count; i++) {
    const t = count > 1 ? i / (count - 1) : 0.5;
    const drift = Math.sin(now / 6800 + i * 2.3) * scene.w * 0.008;
    const cx = scene.x + scene.w * (xFrom + 0.12 + t * (span - 0.24)) + drift;
    const cy = scene.y + scene.h * (0.14 + seeded(i * 4.1) * 0.06);
    const w = scene.w * (0.16 + seeded(i * 2.7) * 0.06) * (dark ? 1.25 : 1);
    const h = scene.h * (dark ? 0.09 : 0.07);
    g.rect(cx - w / 2, cy, w, h).fill({ color, alpha: dark ? 0.75 : 0.55 });
    g.rect(cx - w * 0.3, cy - h * 0.55, w * 0.55, h * 0.6).fill({ color, alpha: dark ? 0.7 : 0.5 });
    if (dark) {
      g.rect(cx - w / 2, cy + h, w, 1.5).fill({ color: 0x1a2742, alpha: 0.5 });
    }
  }
}

// Falling rain: short streaks cycling downward from cloud level to the
// ground. Density and speed scale with intensity.
export function drawRainStreaks(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1, slant = 0.18, speed = 900 } = {}) {
  if (intensity <= 0.02) return;
  const groundY = getGroundY(scene);
  const top = scene.y + scene.h * 0.24;
  const fall = groundY - top;
  const span = xTo - xFrom;
  const columns = Math.max(4, Math.round((6 + intensity * 26) * span));
  for (let i = 0; i < columns; i++) {
    const t = columns > 1 ? i / (columns - 1) : 0.5;
    const baseX = scene.x + scene.w * (xFrom + 0.03 + t * (span - 0.06));
    const seed = seeded(i * 6.7);
    const cycle = ((now / speed) + seed * 3) % 1;
    const y = top + cycle * fall;
    const len = 4 + intensity * 5;
    const x = baseX + seed * scene.w * 0.02;
    const color = i % 3 === 0 ? RAIN_COLORS.waterLight : RAIN_COLORS.water;
    g.moveTo(x, y).lineTo(x - len * slant, y + len);
    g.stroke({ width: 1, color, alpha: 0.3 + intensity * 0.45 });
  }
}

// Puddles on the ground band, growing with intensity.
export function drawPuddles(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1 } = {}) {
  if (intensity <= 0.03) return;
  const groundY = getGroundY(scene);
  const span = xTo - xFrom;
  const count = Math.max(1, Math.round(2 + intensity * 4));
  for (let i = 0; i < count; i++) {
    const cx = scene.x + scene.w * (xFrom + 0.1 + seeded(i * 9.1) * (span - 0.2));
    const rx = scene.w * (0.03 + intensity * 0.05) * (0.7 + seeded(i * 3.7) * 0.6);
    const shimmer = 0.85 + Math.sin(now / 1300 + i * 1.9) * 0.15;
    g.ellipse(cx, groundY + scene.h * 0.05, rx, Math.max(1.5, scene.h * 0.008))
      .fill({ color: RAIN_COLORS.water, alpha: (0.2 + intensity * 0.3) * shimmer });
    g.ellipse(cx, groundY + scene.h * 0.05, rx * 0.55, Math.max(1, scene.h * 0.005))
      .fill({ color: RAIN_COLORS.waterLight, alpha: (0.12 + intensity * 0.2) * shimmer });
  }
}

// Rising water band at street level for the storm scene (anegamiento).
export function drawFloodBand(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1 } = {}) {
  if (intensity <= 0.05) return;
  const groundY = getGroundY(scene);
  const span = xTo - xFrom;
  const h = scene.h * (0.015 + intensity * 0.05);
  const ripple = Math.sin(now / 950) * h * 0.15;
  g.rect(scene.x + scene.w * xFrom, groundY - h + ripple, scene.w * span, h + scene.h * 0.06)
    .fill({ color: RAIN_COLORS.water, alpha: 0.14 + intensity * 0.22 });
  g.rect(scene.x + scene.w * xFrom, groundY - h + ripple, scene.w * span, 1.5)
    .fill({ color: RAIN_COLORS.waterLight, alpha: 0.3 + intensity * 0.3 });
}

// Deterministic drought cracks spreading across the ground band as the dry
// spell grows (the resurrected scorched-ground concept).
export function drawCrackedGround(g, scene, theme, { intensity = 0, xFrom = 0, xTo = 1 } = {}) {
  if (intensity <= 0.04) return;
  const groundY = getGroundY(scene);
  const groundH = Math.max(8, scene.h * 0.1);
  const color = theme.particle || theme.accent;
  const span = xTo - xFrom;
  const marks = Math.round(intensity * 30 * span);
  for (let i = 0; i < marks; i++) {
    const gx = scene.x + scene.w * (xFrom + 0.03 + seeded(i * 5.7) * (span - 0.06));
    const gy = groundY + groundH * (0.15 + seeded(i * 2.9) * 0.65);
    const len = 3 + seeded(i * 8.1) * 7;
    const alpha = 0.16 + intensity * 0.22;
    if (seeded(i * 11.3) > 0.55) {
      g.rect(gx, gy, 1, len).fill({ color, alpha });
      g.rect(gx + 1, gy + len * 0.6, len * 0.4, 1).fill({ color, alpha: alpha * 0.7 });
    } else {
      g.rect(gx, gy, len, 1).fill({ color, alpha });
      g.rect(gx + len * 0.5, gy + 1, 1, len * 0.5).fill({ color, alpha: alpha * 0.7 });
    }
  }
}

// Pixel water tank on a stand: the shell is fixed; the water level DROPS as
// the dry spell grows (intensity 0 = full, 1 = nearly empty). Physical
// instrument, same role as the Tmax thermometer.
export function drawWaterTank(g, scene, theme, { intensity = 0, now = 0, x = 0.1 } = {}) {
  const groundY = getGroundY(scene);
  const tankW = Math.max(16, scene.w * 0.09);
  const tankH = scene.h * 0.3;
  const tx = scene.x + scene.w * x;
  const ty = groundY - tankH - scene.h * 0.08;

  // Legs + shell.
  g.moveTo(tx + 2, groundY).lineTo(tx + 4, ty + tankH);
  g.moveTo(tx + tankW - 2, groundY).lineTo(tx + tankW - 4, ty + tankH);
  g.stroke({ width: 1.5, color: theme.line, alpha: 0.5 });
  g.rect(tx, ty, tankW, tankH).fill({ color: theme.lineSoft, alpha: 0.35 });
  g.rect(tx, ty, tankW, tankH).stroke({ width: 1, color: theme.line, alpha: 0.55 });
  // Level marks.
  for (let i = 1; i < 4; i++) {
    const my = ty + tankH * (i / 4);
    g.moveTo(tx + 1, my).lineTo(tx + 4, my);
    g.stroke({ width: 1, color: theme.line, alpha: 0.3 });
  }

  // Water: level drops with intensity.
  const level = 0.92 - intensity * 0.82;
  const wh = tankH * Math.max(0.06, level);
  const ripple = Math.sin(now / 1600) * 0.6;
  g.rect(tx + 2, ty + tankH - wh + ripple, tankW - 4, wh - ripple - 2)
    .fill({ color: RAIN_COLORS.water, alpha: 0.5 });
  g.rect(tx + 2, ty + tankH - wh + ripple, tankW - 4, 1.5)
    .fill({ color: RAIN_COLORS.waterLight, alpha: 0.6 });
}

// Intermittent lightning bolt: flash frequency and brightness scale with
// intensity. Deterministic gate on the time axis so it strobes naturally.
export function drawLightning(g, scene, theme, { intensity = 0, now = 0, xFrom = 0, xTo = 1 } = {}) {
  if (intensity <= 0.05) return;
  // Gate: a flash window every few seconds, more frequent when intense.
  const period = 4200 - intensity * 2600;
  const phase = (now % period) / period;
  if (phase > 0.09) return;
  const fade = 1 - phase / 0.09;

  const span = xTo - xFrom;
  const which = Math.floor(now / period) % 3;
  const bx = scene.x + scene.w * (xFrom + 0.25 + which * 0.22 * span);
  const top = scene.y + scene.h * 0.22;
  const groundY = getGroundY(scene);

  // Sky flash.
  g.rect(scene.x + scene.w * xFrom, scene.y + scene.h * 0.04, scene.w * span, scene.h * 0.68)
    .fill({ color: RAIN_COLORS.lightning, alpha: 0.05 * fade * intensity });

  // Zig-zag bolt.
  const segs = [[0, 0], [-4, 0.3], [3, 0.55], [-2, 0.8], [1, 1]];
  let px = bx;
  let py = top;
  for (let i = 1; i < segs.length; i++) {
    const nx = bx + segs[i][0] * scene.w * 0.012;
    const ny = top + segs[i][1] * (groundY - top) * 0.85;
    g.moveTo(px, py).lineTo(nx, ny);
    px = nx;
    py = ny;
  }
  g.stroke({ width: 2, color: RAIN_COLORS.lightning, alpha: 0.75 * fade });
}
