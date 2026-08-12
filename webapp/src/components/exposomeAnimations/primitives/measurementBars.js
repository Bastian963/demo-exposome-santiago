import { Graphics } from "pixi.js";

export function drawMeasurementBars({ container, bounds, theme, intensity = 0 }) {
  const g = new Graphics();
  const bars = 12;
  const gap = 3;
  const w = Math.max(3, Math.floor((bounds.width * 0.34) / bars) - gap);
  const h = Math.max(18, bounds.height * 0.12);
  const x0 = bounds.width * 0.58;
  const y0 = bounds.height * 0.78;
  const active = Math.round(Math.max(1, intensity * bars));
  for (let i = 0; i < bars; i++) {
    const barH = h * (0.25 + (i + 1) / bars * 0.75);
    g.rect(x0 + i * (w + gap), y0 + h - barH, w, barH)
      .fill({ color: i < active ? theme.accent : theme.lineSoft, alpha: i < active ? 0.72 : 0.22 });
  }
  container.addChild(g);
  return g;
}
