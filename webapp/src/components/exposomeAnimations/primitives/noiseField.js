import { Graphics } from "pixi.js";

export function drawNoiseField({ container, bounds, theme, intensity = 0, now = 0, count = 60 }) {
  const g = new Graphics();
  const n = Math.max(8, Math.round(count));
  for (let i = 0; i < n; i++) {
    const phase = i * 17.17;
    const x = ((Math.sin(phase * 3.1) * 0.5 + 0.5) * bounds.width + Math.sin(now / 2100 + phase) * 7) % bounds.width;
    const y = ((Math.cos(phase * 2.3) * 0.5 + 0.5) * bounds.height + Math.cos(now / 2600 + phase) * 5) % bounds.height;
    const alpha = 0.08 + intensity * 0.32;
    g.rect(x, y, 1.6, 1.6).fill({ color: theme.accent, alpha });
  }
  container.addChild(g);
  return g;
}
