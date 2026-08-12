export function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

export function clamp01(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function advanceTween({ from, to, startedAt, durationMs, now }) {
  if (!startedAt || durationMs <= 0) return { value: to, done: true };
  const t = clamp01((now - startedAt) / durationMs);
  return {
    value: lerp(from, to, easeOutCubic(t)),
    done: t >= 1,
  };
}
