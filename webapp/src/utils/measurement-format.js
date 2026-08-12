export function formatMeasuredValue(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (value === 0) return "0.00";
  const magnitude = Math.abs(value);
  if (magnitude < 0.01) return value.toExponential(3);
  if (magnitude >= 10_000) {
    return value.toLocaleString("es-CL", { maximumFractionDigits: 0 });
  }
  return value.toFixed(2);
}
