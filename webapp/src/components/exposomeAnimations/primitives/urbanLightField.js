import { Graphics } from "pixi.js";
import { getLampSources, getUrbanSceneRect } from "./pixelCity.js";

export function drawUrbanLightField({ container, bounds, theme, intensity = 0, now = 0 }) {
  const scene = getUrbanSceneRect(bounds);
  const g = new Graphics();
  const breath = Math.sin(now / 3600) * 0.035;
  const horizonY = scene.y + scene.h * 0.8;
  const cx = scene.x + scene.w * 0.5;

  drawSkyGlow(g, scene, theme, intensity, breath, cx, horizonY);
  drawLampHalos(g, bounds, theme, intensity, breath);

  container.addChild(g);
  return g;
}

function drawSkyGlow(g, scene, theme, intensity, breath, cx, horizonY) {
  const baseAlpha = 0.028 + intensity * 0.15;
  for (let i = 0; i < 4; i++) {
    const scale = 0.42 + i * 0.18 + intensity * 0.25 + breath;
    g.ellipse(cx, horizonY - scene.h * (0.08 + i * 0.025), scene.w * scale, scene.h * (0.16 + i * 0.055))
      .fill({ color: theme.accent, alpha: baseAlpha * (1 - i * 0.2) });
  }
}

function drawLampHalos(g, bounds, theme, intensity, breath) {
  const sources = getLampSources(bounds);
  for (let i = 0; i < sources.length; i++) {
    const source = sources[i];
    const radius = bounds.size * (0.045 + intensity * 0.115 + i * 0.006 + breath * 0.2);
    g.circle(source.x, source.y + radius * 0.4, radius * 1.85)
      .fill({ color: theme.accent, alpha: 0.04 + intensity * 0.11 });
    g.circle(source.x, source.y + radius * 0.2, radius * 0.78)
      .fill({ color: theme.accent, alpha: 0.11 + intensity * 0.2 });
  }
}
