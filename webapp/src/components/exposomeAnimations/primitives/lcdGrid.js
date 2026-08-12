import { Graphics } from "pixi.js";

export function drawLcdGrid({ container, bounds, theme, alpha = 0.22 }) {
  const g = new Graphics();
  const step = Math.max(12, Math.round(bounds.size / 18));
  for (let x = step; x < bounds.width; x += step) {
    g.moveTo(x, 0).lineTo(x, bounds.height);
  }
  for (let y = step; y < bounds.height; y += step) {
    g.moveTo(0, y).lineTo(bounds.width, y);
  }
  g.stroke({ width: 1, color: theme.grid, alpha });
  container.addChild(g);
  return g;
}
