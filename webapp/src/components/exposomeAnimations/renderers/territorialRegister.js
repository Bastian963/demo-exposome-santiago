import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";

export function createTerritorialRegisterRenderer(mode = "safety") {
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

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    clear(staticLayer);
    const box = frame(bounds);
    const g = new Graphics();
    g.roundRect(box.x, box.y, box.w, box.h, 7).fill({ color: theme.lcd, alpha: 0.9 });
    g.roundRect(box.x, box.y, box.w, box.h, 7).stroke({ width: 2, color: theme.line, alpha: 0.75 });
    for (let i = 1; i < 6; i += 1) {
      const x = box.x + (box.w * i) / 6;
      g.moveTo(x, box.y + 12).lineTo(x, box.y + box.h - 12)
        .stroke({ width: 1, color: theme.grid, alpha: 0.34 });
    }
    for (let i = 1; i < 4; i += 1) {
      const y = box.y + (box.h * i) / 4;
      g.moveTo(box.x + 12, y).lineTo(box.x + box.w - 12, y)
        .stroke({ width: 1, color: theme.grid, alpha: 0.34 });
    }
    staticLayer.addChild(g);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!same(bounds, lastBounds)) resize(bounds, theme);
    clear(dynamicLayer);
    const t = clamp01(visualState.intensity || 0);
    if (mode === "outcome") drawOutcome(dynamicLayer, frame(bounds), theme, t, now);
    else drawSafety(dynamicLayer, frame(bounds), theme, t, now);
  }

  function destroy() {
    clear(staticLayer);
    clear(dynamicLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
  }

  return { init, resize, update, destroy };
}

function drawSafety(container, box, theme, t, now) {
  const g = new Graphics();
  const roadY = box.y + box.h * 0.62;
  g.rect(box.x + 16, roadY - 4, box.w - 32, 8).fill({ color: theme.lineSoft, alpha: 0.64 });
  for (let i = 0; i < 7; i += 1) {
    const x = box.x + 24 + i * ((box.w - 48) / 7);
    const h = 18 + ((i * 13) % 28);
    g.rect(x, roadY - h, 18, h).fill({ color: theme.surface, alpha: 0.95 });
    g.rect(x + 4, roadY - h + 5, 4, 4).fill({ color: theme.line, alpha: 0.35 });
    g.rect(x + 11, roadY - h + 5, 4, 4).fill({ color: theme.line, alpha: 0.35 });
  }
  const count = Math.round(3 + t * 14);
  for (let i = 0; i < count; i += 1) {
    const seed = (i * 47) % 101;
    const x = box.x + 22 + ((seed * 2.37) % (box.w - 44));
    const y = box.y + 18 + ((seed * 1.61) % (box.h - 38));
    const pulse = 0.35 + 0.35 * Math.sin(now * 0.004 + i * 0.8);
    g.circle(x, y, 3 + pulse * 2).fill({ color: theme.accent, alpha: 0.25 + t * 0.45 });
    g.circle(x, y, 8 + pulse * 4).stroke({ width: 1, color: theme.accent, alpha: 0.08 + t * 0.18 });
  }
  container.addChild(g);
}

function drawOutcome(container, box, theme, t, now) {
  const g = new Graphics();
  const left = box.x + 22, right = box.x + box.w - 18;
  const top = box.y + 18, bottom = box.y + box.h - 20;
  g.moveTo(left, top).lineTo(left, bottom).lineTo(right, bottom)
    .stroke({ width: 2, color: theme.line, alpha: 0.55 });
  const points = 12;
  let previous = null;
  for (let i = 0; i < points; i += 1) {
    const x = left + (i / (points - 1)) * (right - left);
    const base = 0.18 + ((i * 17) % 41) / 64;
    const y = bottom - (base * 0.55 + t * 0.4) * (bottom - top);
    if (previous) g.moveTo(previous.x, previous.y).lineTo(x, y)
      .stroke({ width: 1.5, color: theme.accent, alpha: 0.42 + t * 0.35 });
    const pulse = 0.4 + 0.2 * Math.sin(now * 0.0025 + i);
    g.circle(x, y, 2.5 + pulse).fill({ color: theme.white, alpha: 0.55 + t * 0.3 });
    previous = { x, y };
  }
  g.rect(left, bottom + 7, (right - left) * t, 4).fill({ color: theme.accent, alpha: 0.5 });
  container.addChild(g);
}

function frame(bounds) {
  const pad = Math.max(10, Math.min(bounds.width, bounds.height) * 0.06);
  return { x: pad, y: pad, w: bounds.width - pad * 2, h: bounds.height - pad * 2 };
}

function same(a, b) {
  return !!a && !!b && a.width === b.width && a.height === b.height;
}

function clear(container) {
  if (!container) return;
  for (const child of container.removeChildren()) child.destroy?.({ children: true });
}
