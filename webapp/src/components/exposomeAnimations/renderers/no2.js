import { Container, Graphics } from "pixi.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { drawPixelTraffic, getTrafficFrame } from "../primitives/pixelTraffic.js";

export function createNo2Renderer() {
  let root = null;
  let staticLayer = null;
  let trafficLayer = null;
  let maskGraphics = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    trafficLayer = new Container();
    maskGraphics = new Graphics();
    root.addChild(staticLayer);
    root.addChild(trafficLayer);
    // Cars + exhaust are drawn with absolute coordinates that can drift
    // past the instrument frame at the edges of their travel; a hard
    // rectangular mask keeps everything inside the sensor bezel. Left
    // unparented on purpose: it draws in the same absolute-coordinate
    // space as trafficLayer (no transform offsets to keep in sync), and
    // Pixi doesn't render objects assigned purely as another's mask.
    trafficLayer.mask = maskGraphics;
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    destroyChildren(trafficLayer);
    const intensity = Math.max(0.15, visualState.diffusion ?? visualState.intensity ?? 0);
    drawPixelTraffic({ container: trafficLayer, bounds, theme, intensity, now });
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawSensorFrame(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.11 });
    const frame = getTrafficFrame(bounds);
    maskGraphics.clear();
    maskGraphics.rect(frame.x, frame.y, frame.w, frame.h).fill({ color: 0xffffff });
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(trafficLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    trafficLayer = null;
    maskGraphics = null;
  }

  return { init, update, resize, destroy };
}

function drawSensorFrame(container, bounds, theme) {
  const g = new Graphics();
  const x = bounds.width * 0.08;
  const y = bounds.height * 0.13;
  const w = bounds.width * 0.84;
  const h = bounds.height * 0.68;
  g.rect(x, y, w, h).fill({ color: theme.lcd, alpha: 0.86 });
  g.rect(x, y, w, h).stroke({ width: 2, color: theme.line, alpha: 0.76 });
  g.rect(x + 7, y + 7, w - 14, h - 14).stroke({ width: 1, color: theme.lineSoft, alpha: 0.65 });
  container.addChild(g);
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
