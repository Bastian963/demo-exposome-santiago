import { Container, Graphics, Sprite, Texture } from "pixi.js";
import { DEFAULT_PARTICLE_SCALE, MAX_PARTICLES } from "../constants.js";
import { drawLcdGrid } from "../primitives/lcdGrid.js";
import { drawNoiseField } from "../primitives/noiseField.js";
import { drawSensorDial } from "../primitives/sensorDial.js";

export function createParticlesRenderer(options = {}) {
  const opts = {
    maxParticles: MAX_PARTICLES,
    particleScale: DEFAULT_PARTICLE_SCALE,
    drift: 0.18,
    jitter: 0.014,
    randomJitter: 0.005,
    alpha: 0.58,
    alphaBoost: 0.24,
    depthLayers: 3,
    diffusionField: false,
    diffusionAlpha: 0.12,
    flowX: 0,
    flowY: 0,
    minVisualCount: 0,
    idleIntensity: 0,
    showDial: true,
    sizeBoost: 0,
    ...options,
  };
  let root = null;
  let staticLayer = null;
  let fieldLayer = null;
  let particleLayer = null;
  let fieldGraphics = null;
  let particleTexture = null;
  let particles = [];
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    fieldLayer = new Container();
    particleLayer = new Container();
    fieldGraphics = new Graphics();
    root.addChild(staticLayer);
    root.addChild(fieldLayer);
    root.addChild(particleLayer);
    fieldLayer.addChild(fieldGraphics);
    parent.addChild(root);
    particleTexture = createParticleTexture(opts.texture || "fine");
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    const renderState = withVisualFloor(visualState);
    const rawTarget = Math.max(0, Math.round(renderState.visualCount || 0));
    const target = Math.min(opts.maxParticles, Math.max(opts.minVisualCount, rawTarget));
    updateField(bounds, theme, renderState, now);
    syncParticles(target, bounds, theme);
    updateParticles(bounds, renderState, now);
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawInstrumentChamber(staticLayer, bounds, theme);
    drawLcdGrid({ container: staticLayer, bounds, theme, alpha: 0.12 });
    if (opts.showDial) {
      drawSensorDial({ container: staticLayer, bounds, theme, intensity: 0.35 });
    }
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(fieldLayer);
    destroyChildren(particleLayer);
    if (particleTexture) {
      try { particleTexture.destroy(true); } catch (_) {}
    }
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    fieldLayer = null;
    particleLayer = null;
    fieldGraphics = null;
    particleTexture = null;
    particles = [];
  }

  function updateField(bounds, theme, visualState, now) {
    if (!fieldGraphics) return;
    fieldGraphics.clear();
    if (!opts.diffusionField) return;
    drawDiffusionField(fieldGraphics, bounds, theme, visualState, now, opts);
  }

  function withVisualFloor(visualState = {}) {
    const floor = opts.idleIntensity || 0;
    if (floor <= 0) return visualState;
    const intensity = Math.max(floor, visualState.intensity || 0);
    return {
      ...visualState,
      intensity,
      density: Math.max(floor, visualState.density || 0),
      diffusion: Math.max(floor, visualState.diffusion || 0),
      radiance: Math.max(floor, visualState.radiance || 0),
    };
  }

  function syncParticles(target, bounds, theme) {
    while (particles.length < target) particles.push(spawnParticle(bounds, theme));
    while (particles.length > target) {
      const p = particles.pop();
      if (p?.sprite?.parent) p.sprite.parent.removeChild(p.sprite);
      try { p?.sprite?.destroy(); } catch (_) {}
    }
  }

  function spawnParticle(bounds, theme) {
    const layer = Math.floor(Math.random() * opts.depthLayers);
    const sprite = new Sprite(particleTexture);
    const depth = opts.depthLayers > 1 ? layer / (opts.depthLayers - 1) : 0;
    const baseScale = opts.particleScale * (0.72 + depth * 0.42);
    sprite.anchor.set(0.5, 0.5);
    sprite.scale.set(baseScale);
    sprite.tint = opts.tint || theme.particle || theme.accent;
    sprite.alpha = 0;
    sprite.x = bounds.width * (0.12 + Math.random() * 0.76);
    sprite.y = bounds.height * (0.18 + Math.random() * 0.6);
    particleLayer.addChild(sprite);
    return {
      sprite,
      layer,
      baseScale,
      x: sprite.x,
      y: sprite.y,
      vx: (Math.random() - 0.5) * opts.drift,
      vy: (Math.random() - 0.5) * opts.drift,
      phase: Math.random() * Math.PI * 2,
      radius: 0.55 + Math.random() * 0.45,
      alpha: 0,
    };
  }

  function updateParticles(bounds, visualState, now) {
    const left = bounds.width * 0.1;
    const right = bounds.width * 0.9;
    const top = bounds.height * 0.16;
    const bottom = bounds.height * 0.78;
    const intensity = visualState.intensity || 0;
    const flowScale = 0.28 + intensity * 0.95;
    const flowX = (opts.flowX || 0) * flowScale;
    const flowY = (opts.flowY || 0) * flowScale;
    for (const p of particles) {
      const slowNoise = Math.sin(now / 3200 + p.phase) * opts.jitter;
      const verticalNoise = Math.cos(now / 3900 + p.phase * 0.7) * opts.jitter;
      p.vx += slowNoise + flowX + (Math.random() - 0.5) * opts.randomJitter;
      p.vy += verticalNoise * 0.55 + flowY + (Math.random() - 0.5) * opts.randomJitter * 0.65;
      p.vx *= 0.965;
      p.vy *= 0.965;
      p.x += p.vx + Math.sin(now / 4600 + p.phase) * 0.012;
      p.y += p.vy + Math.cos(now / 5100 + p.phase) * 0.01;
      if (p.x < left) p.x = right;
      if (p.x > right) p.x = left;
      if (p.y < top) p.y = bottom;
      if (p.y > bottom) p.y = top;
      p.alpha += ((opts.alpha + intensity * opts.alphaBoost) - p.alpha) * 0.035;
      p.sprite.x = p.x;
      p.sprite.y = p.y;
      p.sprite.alpha = Math.max(0.12, Math.min(0.94, p.alpha - p.layer * 0.055));
      if (opts.sizeBoost) {
        p.sprite.scale.set(p.baseScale * (1 + intensity * opts.sizeBoost));
      }
    }
  }

  return { init, update, resize, destroy };
}

function drawDiffusionField(g, bounds, theme, visualState, now, opts) {
  const intensity = Math.max(0, Math.min(1, visualState.diffusion || visualState.intensity || 0));
  if (intensity <= 0.01) return;
  const frame = {
    x: bounds.width * 0.08,
    y: bounds.height * 0.13,
    w: bounds.width * 0.84,
    h: bounds.height * 0.68,
  };
  const color = theme.particle || theme.accent;
  const alpha = opts.diffusionAlpha * (0.42 + intensity * 1.15);

  for (let i = 0; i < 8; i++) {
    const t = i / 7;
    const phase = now / (5200 + i * 650) + i * 1.7;
    const cx = frame.x + frame.w * (0.18 + t * 0.68 + Math.sin(phase) * 0.018);
    const cy = frame.y + frame.h * (0.25 + ((i * 0.17) % 0.46) + Math.cos(phase * 0.8) * 0.018);
    const rx = frame.w * (0.17 + intensity * 0.17 + t * 0.025);
    const ry = frame.h * (0.052 + intensity * 0.052);
    g.ellipse(cx, cy, rx, ry).fill({ color, alpha: alpha * (1 - i * 0.065) });
  }

  for (let i = 0; i < 16; i++) {
    const t = i / 15;
    const y = frame.y + frame.h * (0.22 + t * 0.5);
    const drift = ((now / 95 + i * 37) % (frame.w * 0.24)) - frame.w * 0.12;
    const x = frame.x + frame.w * (0.16 + ((i * 0.071) % 0.64)) + drift * 0.08;
    const len = frame.w * (0.075 + intensity * 0.08);
    g.moveTo(x, y).lineTo(x + len, y + Math.sin(now / 1700 + i) * frame.h * 0.01);
  }
  g.stroke({ width: 2, color, alpha: Math.min(0.55, alpha * 1.12) });
}

function drawInstrumentChamber(container, bounds, theme) {
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

function createParticleTexture(kind) {
  const size = kind === "suspended" ? 5 : kind === "fine" ? 4 : kind === "gas" ? 4 : 5;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, size, size);
  if (kind === "gas") {
    ctx.globalAlpha = 0.38;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(1, 1, 2, 2);
    ctx.globalAlpha = 0.85;
    ctx.fillRect(2, 2, 1, 1);
  } else if (kind === "suspended") {
    ctx.globalAlpha = 0.24;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(1, 1, 3, 3);
    ctx.globalAlpha = 0.68;
    ctx.fillRect(2, 1, 1, 3);
    ctx.fillRect(1, 2, 3, 1);
    ctx.globalAlpha = 1;
    ctx.fillRect(2, 2, 1, 1);
  } else {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(Math.floor(size / 2), Math.floor(size / 2), 1, 1);
    if (kind !== "fine") {
      ctx.globalAlpha = 0.45;
      ctx.fillRect(1, 1, 2, 2);
    }
  }
  return Texture.from(canvas);
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

export function drawAmbientNoise(container, bounds, theme, intensity, now) {
  drawNoiseField({
    container,
    bounds,
    theme,
    intensity,
    now,
    count: 20 + intensity * 50,
  });
}
