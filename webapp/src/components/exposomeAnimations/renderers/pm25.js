import { createParticlesRenderer } from "./particlesBase.js";

export function createPm25Renderer() {
  return createParticlesRenderer({
    maxParticles: 720,
    particleScale: 1.3,
    drift: 0.08,
    jitter: 0.009,
    randomJitter: 0.003,
    alpha: 0.45,
    alphaBoost: 0.48,
    sizeBoost: 0.6,
    depthLayers: 5,
    texture: "suspended",
    showDial: false,
  });
}
