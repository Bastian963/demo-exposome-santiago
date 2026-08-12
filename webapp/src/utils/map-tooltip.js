import { formatMeasuredValue } from "./measurement-format.js";

function escHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function communeNameAtPoint(map, point, fallback = "") {
  try {
    const feature = map?.queryRenderedFeatures?.(point, { layers: ["communes-fill"] })?.[0];
    return String(feature?.properties?.name || fallback || "").trim();
  } catch (_) {
    return String(fallback || "").trim();
  }
}

export function mapTooltipHtml({
  communeName,
  metricLabel,
  value,
  valueText,
  unit,
  supportLabel,
}) {
  const numeric = Number(value);
  const measured = typeof valueText === "string" && valueText.trim()
    ? valueText.trim()
    : Number.isFinite(numeric) ? formatMeasuredValue(numeric) : "Sin dato";
  const aria = [communeName, metricLabel, measured, unit, supportLabel]
    .filter(Boolean)
    .join(", ");
  return `
    <div class="map-value-tooltip" role="status" aria-label="${escHtml(aria)}">
      <div class="pixel-popup-name">${escHtml(communeName || "Ubicación sin nombre")}</div>
      <div class="pixel-popup-value">
        <span class="pixel-popup-label">${escHtml(metricLabel)}:</span>
        <strong>${escHtml(measured)}</strong>
        <span class="pixel-popup-unit">${escHtml(unit)}</span>
      </div>
      <div class="pixel-popup-meta">${escHtml(supportLabel)}</div>
    </div>
  `;
}
