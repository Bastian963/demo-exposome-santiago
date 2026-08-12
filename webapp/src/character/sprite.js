// PIXI sprite for CreeperLat.
// v0.5: idle + walking sprite sheets. The character is anchored
// in the bottom-right corner. The PIXI renderer is a fixed-size
// container that floats over the MapLibre canvas.

import { Application, Assets, Sprite, Texture, Rectangle } from "pixi.js";
import { getPalette } from "../palette.js";
import { prefersReducedMotion } from "../utils/motion.js";

let _app = null;
let _creeper = null;
let _walkingFrames = null;
let _idleFrames = null;
let _isWalking = false;
let _walkAnim = null;

export async function setupCharacter(containerId = "characterContainer") {
  const container = document.getElementById(containerId);
  if (!container) throw new Error(`#${containerId} not found`);

  const palette = getPalette();
  const tintColor = parseInt(palette.character["body_main"].slice(1), 16);

  _app = new Application();
  await _app.init({
    width: 96,
    height: 96,
    backgroundAlpha: 0,
    antialias: false,
    resolution: 1,
    autoDensity: false,
  });
  container.appendChild(_app.canvas);

  // Load sprite sheets.
  const idleTex = await Assets.load("/sprites/character/idle.png");
  const walkTex = await Assets.load("/sprites/character/walking.png");

  // Slice into 32x32 frames (sprite sheets are 4 frames wide).
  _idleFrames = sliceFrames(idleTex, 4);
  _walkingFrames = sliceFrames(walkTex, 4);

  _creeper = new Sprite(_idleFrames[0]);
  _creeper.tint = tintColor;
  _creeper.anchor.set(0.5, 1.0); // anchor at feet
  _creeper.x = 48;
  _creeper.y = 92;
  _creeper.scale.set(2.5, 2.5); // 32x32 -> 80x80
  _app.stage.addChild(_creeper);

  // Idle animation: blink cycle.
  startIdle();
}

function sliceFrames(texture, count) {
  const frameW = texture.width / count;
  const frameH = texture.height;
  const frames = [];
  for (let i = 0; i < count; i++) {
    const rect = new Rectangle(i * frameW, 0, frameW, frameH);
    const frameTex = new Texture({
      source: texture.source,
      frame: rect,
    });
    frames.push(frameTex);
  }
  return frames;
}

function startIdle() {
  if (!_creeper || !_idleFrames) return;
  _isWalking = false;
  if (_walkAnim) {
    _walkAnim.stop();
    _walkAnim = null;
  }
  // Reduced motion: the character stands on its first frame.
  if (prefersReducedMotion()) {
    _creeper.texture = _idleFrames[0];
    return;
  }
  let i = 0;
  _app.ticker.add(() => {
    if (_isWalking) return;
    i = (i + 0.02) % _idleFrames.length;
    const idx = Math.floor(i);
    _creeper.texture = _idleFrames[idx];
  });
}

export function walkTo(targetX, targetY, duration = 600) {
  if (!_creeper) return Promise.resolve();
  // Reduced motion: jump straight to the destination, no walk cycle.
  if (prefersReducedMotion()) {
    _creeper.x = targetX;
    _creeper.y = targetY;
    startIdle();
    return Promise.resolve();
  }
  _isWalking = true;
  if (_walkAnim) _walkAnim.stop();

  // Swap to walking frames.
  let frameIdx = 0;
  const walkTicker = () => {
    frameIdx = (frameIdx + 0.18) % _walkingFrames.length;
    _creeper.texture = _walkingFrames[Math.floor(frameIdx)];
  };
  _app.ticker.add(walkTicker);

  const start = { x: _creeper.x, y: _creeper.y };
  const end = { x: targetX, y: targetY };
  return new Promise((resolve) => {
    const t0 = performance.now();
    const animate = () => {
      const t = Math.min(1, (performance.now() - t0) / duration);
      // Ease in-out
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      _creeper.x = start.x + (end.x - start.x) * e;
      _creeper.y = start.y + (end.y - start.y) * e;
      if (t < 1) {
        requestAnimationFrame(animate);
      } else {
        _app.ticker.remove(walkTicker);
        startIdle();
        resolve();
      }
    };
    requestAnimationFrame(animate);
  });
}

export function setMood(spriteName = "active") {
  if (!_creeper) return;
  if (spriteName === "active") {
    // Use mask variant
    Assets.load("/sprites/character/active.png").then((tex) => {
      _creeper.texture = new Texture({ source: tex.source, frame: { x: 0, y: 0, width: 32, height: 32 } });
    });
  } else if (spriteName === "idle") {
    startIdle();
  }
}
