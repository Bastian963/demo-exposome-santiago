import { Graphics } from "pixi.js";

export function drawSensorDial({ container, bounds, theme, intensity = 0 }) {
  const g = new Graphics();
  const cx = bounds.width * 0.2;
  const cy = bounds.height * 0.78;
  const r = Math.max(18, bounds.size * 0.075);
  const start = Math.PI * 0.82;
  const end = Math.PI * 2.18;
  const angle = start + (end - start) * Math.max(0, Math.min(1, intensity));

  g.arc(cx, cy, r, start, end);
  g.stroke({ width: 2, color: theme.lineSoft, alpha: 0.55 });
  g.arc(cx, cy, r, start, angle);
  g.stroke({ width: 3, color: theme.accent, alpha: 0.78 });
  g.moveTo(cx, cy).lineTo(cx + Math.cos(angle) * r * 0.78, cy + Math.sin(angle) * r * 0.78);
  g.stroke({ width: 1, color: theme.line, alpha: 0.65 });
  g.circle(cx, cy, 2.4).fill({ color: theme.line, alpha: 0.8 });
  container.addChild(g);
  return g;
}
