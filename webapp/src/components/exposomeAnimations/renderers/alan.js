import { Container, Graphics } from "pixi.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { drawPixelCity } from "../primitives/pixelCity.js";
import { drawUrbanLightField } from "../primitives/urbanLightField.js";

export function createAlanRenderer() {
  let root = null;
  let staticLayer = null;
  let radianceLayer = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    radianceLayer = new Container();
    root.addChild(staticLayer);
    root.addChild(radianceLayer);
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    destroyChildren(radianceLayer);
    const intensity = visualState.radiance || visualState.intensity || 0;
    drawUrbanLightField({ container: radianceLayer, bounds, theme, intensity, now });
    drawPixelCity({ container: radianceLayer, bounds, theme, intensity, now });
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawSensorFrame(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.11 });
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(radianceLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    radianceLayer = null;
  }

  return { init, update, resize, destroy };
}

function drawSensorFrame(container, bounds, theme) {
  const g = new Graphics();
  const x = bounds.width * 0.08;
  const y = bounds.height * 0.13;
  const w = bounds.width * 0.84;
  const h = bounds.height * 0.68;
  g.rect(x, y, w, h).fill({ color: theme.lcd, alpha: 0.8 });
  g.rect(x, y, w, h).stroke({ width: 2, color: theme.line, alpha: 0.76 });
  g.rect(x + 10, y + 10, w - 20, h - 20).stroke({ width: 1, color: theme.lineSoft, alpha: 0.5 });
  g.moveTo(x + 14, y + h * 0.74).lineTo(x + w - 14, y + h * 0.74);
  g.stroke({ width: 1, color: theme.lineSoft, alpha: 0.3 });
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
