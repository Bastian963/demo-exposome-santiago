// Shared OS-level motion preference. JS animation loops (PIXI tickers,
// requestAnimationFrame) can't be gated by the CSS media query, so they
// check this instead: scenes render their fixed elements as a static
// frame and skip the loop.

const _query = typeof window !== "undefined" && window.matchMedia
  ? window.matchMedia("(prefers-reduced-motion: reduce)")
  : null;

export function prefersReducedMotion() {
  return Boolean(_query?.matches);
}

// Notify listeners when the OS preference flips mid-session (e.g. the
// user toggles it in system settings). Returns an unsubscribe function.
export function onReducedMotionChange(callback) {
  if (!_query?.addEventListener) return () => {};
  const handler = () => callback(_query.matches);
  _query.addEventListener("change", handler);
  return () => _query.removeEventListener("change", handler);
}
