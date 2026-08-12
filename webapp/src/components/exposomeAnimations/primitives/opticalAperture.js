import { Graphics } from "pixi.js";

export function drawOpticalAperture({ container, bounds, theme, intensity = 0, now = 0 }) {
  const g = new Graphics();
  const cx = bounds.cx;
  const cy = bounds.height * 0.42;
  const r = bounds.size * (0.13 + intensity * 0.13);
  const pulse = Math.sin(now / 1800) * 0.015;

  g.circle(cx, cy, bounds.size * 0.2).stroke({ width: 1, color: theme.line, alpha: 0.48 });
  g.circle(cx, cy, bounds.size * 0.29).stroke({ width: 1, color: theme.line, alpha: 0.48 });

  g.circle(cx, cy, r * (1.65 + pulse)).fill({ color: theme.accent, alpha: 0.12 + intensity * 0.2 });

  g.circle(cx, cy, r * 0.76).fill({ color: theme.accent, alpha: 0.2 + intensity * 0.48 });

  g.circle(cx, cy, Math.max(5, r * 0.18)).fill({ color: theme.white, alpha: 0.92 });

  g.moveTo(cx - bounds.size * 0.34, cy).lineTo(cx + bounds.size * 0.34, cy);
  g.moveTo(cx, cy - bounds.size * 0.34).lineTo(cx, cy + bounds.size * 0.34);
  g.stroke({ width: 1, color: theme.line, alpha: 0.5 });
  container.addChild(g);
  return g;
}
