import {
  init,
  destroy,
  configure,
  setValue as setControllerValue,
  previewValue as previewControllerValue,
  clearPreviewValue as clearControllerPreviewValue,
  setStudyDomain as setControllerStudyDomain,
  getStateForTests,
  whoCategory,
  whoCategoryLabel,
} from "./controller.js";
import { valueToCount } from "./scaling.js";
import { easeOutCubic } from "./transitions.js";
import { MAX_PARTICLES, DEFAULT_PARTICLE_SCALE as PARTICLE_SCALE, DEFAULT_TWEEN_MS as TWEEN_MS, WHO_THRESHOLDS } from "./constants.js";

export {
  MAX_PARTICLES,
  PARTICLE_SCALE,
  TWEEN_MS,
  WHO_THRESHOLDS,
  valueToCount,
  whoCategory,
  whoCategoryLabel,
  easeOutCubic,
};

export function initAirchamber(containerId = "airchamberCanvas") {
  return init(containerId);
}

export function destroyAirchamber() {
  destroy();
}

export function setChamberCopy(expo) {
  configure(expo);
}

export function setValue(value) {
  setControllerValue(value);
}

export function previewValue(value, context = {}) {
  previewControllerValue(value, context);
}

export function clearPreviewValue() {
  clearControllerPreviewValue();
}

export function setStudyDomain(stats) {
  setControllerStudyDomain(stats);
}

export function _resetForTests() {
  destroy();
}

export function _getStateForTests() {
  return getStateForTests();
}
