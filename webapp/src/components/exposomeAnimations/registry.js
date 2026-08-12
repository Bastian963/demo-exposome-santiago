import { RENDERER_IDS } from "./constants.js";
import { getRendererId } from "./scaling.js";
import { createPm25Renderer } from "./renderers/pm25.js";
import { createNo2Renderer } from "./renderers/no2.js";
import { createAlanRenderer } from "./renderers/alan.js";
import { createHeatRenderer } from "./renderers/heat.js";
import { createRainRenderer } from "./renderers/rain.js";
import { createSocialRenderer } from "./renderers/social.js";
import { createNoiseRenderer } from "./renderers/noise.js";
import { createFoodRenderer } from "./renderers/food.js";
import { createTerritorialRegisterRenderer } from "./renderers/territorialRegister.js";
import { createWalkRenderer } from "./renderers/walk.js";
import { createGreenRenderer } from "./renderers/green.js";
import { createWindRenderer } from "./renderers/wind.js";

export function createRendererForExposome(expo) {
  const rendererId = getRendererId(expo);
  if (rendererId === RENDERER_IDS.RAIN) return { id: rendererId, renderer: createRainRenderer() };
  if (rendererId === RENDERER_IDS.HEAT) return { id: rendererId, renderer: createHeatRenderer() };
  if (rendererId === RENDERER_IDS.NOISE) return { id: rendererId, renderer: createNoiseRenderer() };
  if (rendererId === RENDERER_IDS.FOOD) return { id: rendererId, renderer: createFoodRenderer() };
  if (rendererId === RENDERER_IDS.SAFETY) return { id: rendererId, renderer: createTerritorialRegisterRenderer("safety") };
  if (rendererId === RENDERER_IDS.OUTCOME) return { id: rendererId, renderer: createTerritorialRegisterRenderer("outcome") };
  if (rendererId === RENDERER_IDS.WALK) return { id: rendererId, renderer: createWalkRenderer() };
  if (rendererId === RENDERER_IDS.GREEN) return { id: rendererId, renderer: createGreenRenderer() };
  if (rendererId === RENDERER_IDS.WIND) return { id: rendererId, renderer: createWindRenderer() };
  if (rendererId === RENDERER_IDS.SOCIAL) return { id: rendererId, renderer: createSocialRenderer() };
  if (rendererId === RENDERER_IDS.ALAN) return { id: rendererId, renderer: createAlanRenderer() };
  if (rendererId === RENDERER_IDS.NO2) return { id: rendererId, renderer: createNo2Renderer() };
  return { id: RENDERER_IDS.PM25, renderer: createPm25Renderer() };
}
