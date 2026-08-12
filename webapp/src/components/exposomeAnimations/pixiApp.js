import { Application, Container } from "pixi.js";
import { MIN_CANVAS_SIZE } from "./constants.js";

export async function createPixiApp(container) {
  const ready = await waitForVisibleContainer(container);
  if (!ready) return null;
  const app = new Application();
  await app.init({
    width: Math.max(MIN_CANVAS_SIZE, container.clientWidth || 0),
    height: Math.max(MIN_CANVAS_SIZE, container.clientHeight || 0),
    backgroundAlpha: 0,
    antialias: false,
    resolution: 1,
    autoDensity: true,
  });
  app.canvas.style.width = "100%";
  app.canvas.style.height = "100%";
  app.canvas.style.display = "block";
  container.replaceChildren(app.canvas);

  const root = new Container();
  app.stage.addChild(root);

  const instance = { app, root, container, resizeObserver: null };
  const ro = new ResizeObserver(() => resizePixiApp(instance));
  ro.observe(container);
  instance.resizeObserver = ro;
  return instance;
}

export function getBounds(instance) {
  if (!instance?.app) return { width: 0, height: 0, size: 0 };
  const width = instance.app.renderer.width;
  const height = instance.app.renderer.height;
  return {
    width,
    height,
    size: Math.min(width, height),
    cx: width / 2,
    cy: height / 2,
  };
}

export function resizePixiApp(instance) {
  if (!instance?.app || !instance.container) return;
  const width = Math.max(MIN_CANVAS_SIZE, instance.container.clientWidth || 0);
  const height = Math.max(MIN_CANVAS_SIZE, instance.container.clientHeight || 0);
  instance.app.renderer.resize(width, height);
}

export function destroyPixiApp(instance) {
  if (!instance) return;
  try {
    instance.resizeObserver?.disconnect();
    instance.app?.destroy(true, { children: true, texture: true });
  } catch (e) {
    // PIXI can throw during teardown when transient graphics are already gone.
  }
  if (instance.container) instance.container.replaceChildren();
}

async function waitForVisibleContainer(container) {
  if (!container) return false;
  if (container.clientWidth > 0 && container.clientHeight > 0) return true;
  return new Promise((resolve) => {
    let attempts = 0;
    const ro = new ResizeObserver(() => {
      if (container.clientWidth > 0 && container.clientHeight > 0) {
        cleanup(true);
      }
    });
    const poll = setInterval(() => {
      attempts += 1;
      if (container.clientWidth > 0 && container.clientHeight > 0) {
        cleanup(true);
      } else if (attempts > 30) {
        cleanup(false);
      }
    }, 200);
    const cleanup = (result) => {
      clearInterval(poll);
      ro.disconnect();
      resolve(result);
    };
    ro.observe(container);
  });
}
