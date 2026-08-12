// Pure, renderer-independent translations for monitors whose raw values carry
// a meaningful count or percentage. Keeping them here makes the visual claims
// testable without importing PIXI or a browser runtime.

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function isMeasuredValue(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function segmentedCount(value, { blockSize, maxBlocks }) {
  if (!isMeasuredValue(value) || value <= 0) return 0;
  return clamp(Math.ceil(value / blockSize), 0, maxBlocks);
}

export function percentageCellCount(value, maxCells = 100) {
  if (!isMeasuredValue(value) || value <= 0) return 0;
  return clamp(Math.round(value), 0, maxCells);
}

// Angular velocity is intentionally relative to the active study domain; it
// is not an estimate of a real turbine's RPM. A measured zero stays stopped,
// while a positive low value remains visibly alive.
export function rotorRadiansPerSecond(value, intensity) {
  if (!isMeasuredValue(value) || value <= 0) return 0;
  return 0.35 + clamp(Number(intensity) || 0, 0, 1) * 3.65;
}

export function parkAccessState(value, intensity, noParkSentinel = 99999) {
  if (!isMeasuredValue(value)) return { status: "unavailable", distanceT: 0 };
  if (value >= noParkSentinel) return { status: "no_park_mapped", distanceT: 1 };
  return {
    status: "available",
    distanceT: clamp(Number(intensity) || 0, 0, 1),
  };
}
