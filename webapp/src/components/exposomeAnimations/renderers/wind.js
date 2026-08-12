import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";
import { isMeasuredValue, rotorRadiansPerSecond } from "../monitorSemantics.js";
import { drawUnavailableState } from "../primitives/monitorState.js";

// A small reference wind farm, not a claim that turbines exist in a commune.
// The fixed terrain and towers make rotor speed and wind streaks legible as a
// relative instrument for wind_speed_mean at 10 m.
export function createWindRenderer() {
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
    const scene = getScene(bounds);
    if (!isMeasuredValue(visualState.displayValue)) {
      const unavailable = new Graphics();
      drawUnavailableState(unavailable, scene, theme);
      dynamicLayer.addChild(unavailable);
      return;
    }
    drawWindField(dynamicLayer, scene, theme, visualState, now);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawFrame(staticLayer, bounds, theme);
    drawTerrainAndTowers(staticLayer, getScene(bounds), theme);
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

function turbineLayout(scene) {
  return [
    { x: 0.2, y: 0.67, scale: 0.58, phase: 0.4 },
    { x: 0.52, y: 0.7, scale: 1, phase: 2.1 },
    { x: 0.82, y: 0.69, scale: 0.72, phase: 4.3 },
  ].map((item) => ({
    ...item,
    cx: scene.x + scene.w * item.x,
    hubY: scene.y + scene.h * item.y - scene.h * 0.34 * item.scale,
    groundY: scene.y + scene.h * item.y,
  }));
}

function drawTerrainAndTowers(container, scene, theme) {
  const g = new Graphics();
  const horizonY = scene.y + scene.h * 0.63;
  g.rect(scene.x, scene.y, scene.w, horizonY - scene.y).fill({ color: 0x101a30, alpha: 0.4 });
  g.moveTo(scene.x, horizonY + 5)
    .lineTo(scene.x + scene.w * 0.22, horizonY - 8)
    .lineTo(scene.x + scene.w * 0.5, horizonY + 2)
    .lineTo(scene.x + scene.w * 0.77, horizonY - 11)
    .lineTo(scene.x + scene.w, horizonY + 4)
    .lineTo(scene.x + scene.w, scene.y + scene.h)
    .lineTo(scene.x, scene.y + scene.h)
    .closePath()
    .fill({ color: theme.lineSoft, alpha: 0.46 });
  g.moveTo(scene.x, horizonY + 5).lineTo(scene.x + scene.w, horizonY + 4)
    .stroke({ width: 1, color: theme.line, alpha: 0.35 });

  for (const turbine of turbineLayout(scene)) {
    const towerW = Math.max(2.2, scene.w * 0.009 * turbine.scale);
    g.moveTo(turbine.cx - towerW, turbine.groundY)
      .lineTo(turbine.cx - towerW * 0.32, turbine.hubY)
      .lineTo(turbine.cx + towerW * 0.32, turbine.hubY)
      .lineTo(turbine.cx + towerW, turbine.groundY)
      .closePath()
      .fill({ color: theme.line, alpha: 0.58 });
    g.rect(turbine.cx - towerW * 1.2, turbine.hubY - towerW * 0.75, towerW * 2.4, towerW * 1.5)
      .fill({ color: theme.lcdMuted, alpha: 0.72 });
  }
  container.addChild(g);
}

function drawWindField(container, scene, theme, visualState, now) {
  const g = new Graphics();
  const t = clamp01(visualState.intensity ?? 0);
  const omega = rotorRadiansPerSecond(visualState.displayValue, t);
  const accent = theme.particle || theme.accent;

  drawWindStreaks(g, scene, theme, t, now);
  for (const turbine of turbineLayout(scene)) {
    drawRotor(g, turbine, theme, accent, omega, now);
  }
  drawRelativeGauge(g, scene, theme, t);
  container.addChild(g);
}

function drawRotor(g, turbine, theme, accent, omega, now) {
  const radius = Math.max(10, turbine.scale * 22);
  const angle = now / 1000 * omega + turbine.phase;
  const blurAlpha = omega > 1.4 ? Math.min(0.22, (omega - 1.4) * 0.08) : 0;
  if (blurAlpha) {
    g.circle(turbine.cx, turbine.hubY, radius * 1.02).stroke({ width: 1.5, color: accent, alpha: blurAlpha });
  }
  for (let blade = 0; blade < 3; blade += 1) {
    const a = angle + blade * (Math.PI * 2 / 3);
    const tipX = turbine.cx + Math.cos(a) * radius;
    const tipY = turbine.hubY + Math.sin(a) * radius;
    const sideX = turbine.cx + Math.cos(a + 0.34) * radius * 0.34;
    const sideY = turbine.hubY + Math.sin(a + 0.34) * radius * 0.34;
    g.moveTo(turbine.cx, turbine.hubY).lineTo(tipX, tipY).lineTo(sideX, sideY).closePath()
      .fill({ color: accent, alpha: 0.42 + Math.min(omega, 3) * 0.1 });
  }
  g.circle(turbine.cx, turbine.hubY, Math.max(2.6, turbine.scale * 3.5)).fill({ color: theme.white, alpha: 0.82 });
}

function drawWindStreaks(g, scene, theme, t, now) {
  const streaks = 2 + Math.round(t * 8);
  const speed = 2200 - t * 1550;
  for (let i = 0; i < streaks; i += 1) {
    const seed = seeded(i * 8.7);
    const phase = ((now + seed * speed) % speed) / speed;
    const x = scene.x + scene.w * (phase * 1.1 - 0.08);
    const y = scene.y + scene.h * (0.12 + seed * 0.42);
    const len = scene.w * (0.035 + t * 0.09);
    g.moveTo(x - len, y).lineTo(x, y)
      .stroke({ width: 1.2, color: theme.lcdMuted, alpha: 0.18 + t * 0.35 });
  }
}

function drawRelativeGauge(g, scene, theme, t) {
  const x = scene.x + scene.w * 0.08;
  const y = scene.y + scene.h * 0.86;
  const w = scene.w * 0.84;
  const h = Math.max(4, scene.h * 0.025);
  const accent = theme.particle || theme.accent;
  g.roundRect(x, y, w, h, h / 2).stroke({ width: 1, color: theme.line, alpha: 0.5 });
  if (t > 0) g.roundRect(x + 1, y + 1, Math.max(2, (w - 2) * t), h - 2, (h - 2) / 2)
    .fill({ color: accent, alpha: 0.56 });
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
