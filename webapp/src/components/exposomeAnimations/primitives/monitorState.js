// A deliberately quiet unavailable-state marker. The numeric display already
// renders an em dash; this prevents a missing value from looking like a zero
// intensity scene without adding text that would compete with the panel copy.
export function drawUnavailableState(g, scene, theme) {
  const color = theme.lcdMuted || theme.line;
  g.rect(scene.x, scene.y, scene.w, scene.h).fill({ color: theme.lcd, alpha: 0.42 });
  for (let offset = -scene.h; offset < scene.w; offset += 11) {
    g.moveTo(scene.x + offset, scene.y + scene.h)
      .lineTo(scene.x + offset + scene.h, scene.y);
    g.stroke({ width: 1, color, alpha: 0.14 });
  }
  const cx = scene.x + scene.w * 0.5;
  const cy = scene.y + scene.h * 0.5;
  g.circle(cx, cy, Math.max(7, scene.w * 0.045)).stroke({ width: 1.5, color, alpha: 0.55 });
  g.moveTo(cx - 4, cy).lineTo(cx + 4, cy).stroke({ width: 1.5, color, alpha: 0.65 });
}
