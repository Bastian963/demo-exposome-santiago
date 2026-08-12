function resolutionText(resolution) {
  if (!resolution || typeof resolution !== "object") return "";
  const unit = resolution.unit || "";
  if (resolution.value !== null && resolution.value !== "" && Number.isFinite(Number(resolution.value))) {
    return `${Number(resolution.value).toLocaleString("es-CL", { maximumFractionDigits: 2 })} ${unit}`.trim();
  }
  if (resolution.x !== null && resolution.y !== null
    && Number.isFinite(Number(resolution.x)) && Number.isFinite(Number(resolution.y))) {
    const x = Number(resolution.x).toLocaleString("es-CL", { maximumFractionDigits: 3 });
    const y = Number(resolution.y).toLocaleString("es-CL", { maximumFractionDigits: 3 });
    return `${x} × ${y} ${unit}`.trim();
  }
  return unit === "vector" ? "geometría vectorial" : "";
}

function labelledSupport(support) {
  if (!support || typeof support !== "object") return "";
  const resolution = resolutionText(support.resolution);
  return [support.label, resolution].filter(Boolean).join(" · ");
}

export function mapSupportLabel(spatial, fallback = "unidad administrativa") {
  if (!spatial) return fallback;
  const rendered = spatial.rendered;
  if (rendered?.kind === "administrative_polygon") {
    return rendered.label || "unidad administrativa";
  }
  return labelledSupport(rendered)
    || labelledSupport(spatial.analysis)
    || fallback;
}

export function spatialSupportText(spatial, fallback = "unidad administrativa") {
  if (!spatial) return fallback;
  const map = mapSupportLabel(spatial, fallback);
  if (!spatial.detail) {
    const source = labelledSupport(spatial.downloaded || spatial.source);
    return source && source !== map
      ? `Mapa: ${map}; fuente: ${source}`
      : `Mapa: ${map}`;
  }
  const observation = labelledSupport(spatial.observation);
  const analysis = labelledSupport(spatial.analysis);
  const context = observation && observation !== analysis
    ? `; soporte observacional: ${observation}`
    : "";
  return `Mapa: ${map}${context}`;
}

export function mapSupportPrefix(spatial) {
  if (spatial?.detail?.type === "vector_contours") return "Contorno";
  return spatial?.detail ? "Celda" : "Mapa";
}

export function withMapSupport(exposome, spatial) {
  return {
    ...(exposome || {}),
    spatial,
    resolution: mapSupportLabel(spatial, exposome?.resolution),
  };
}

export function temporalMapLabel(exposome, currentYear = "avg") {
  const detailTemporal = exposome?.detailActive
    ? exposome?.spatial?.detail?.temporal_support
    : null;
  if (detailTemporal?.kind === "year") {
    return `${detailTemporal.source_label} ${detailTemporal.year}`;
  }
  if (detailTemporal?.kind === "period") {
    return `${detailTemporal.source_label} ${detailTemporal.start_year}–${detailTemporal.end_year} · promedio`;
  }
  if (exposome?.yearLabel) {
    const source = exposome.sourceLabel || exposome.period;
    return `${source ? `${source} ` : ""}${exposome.yearLabel}`;
  }
  if (currentYear === "avg") {
    return exposome?.period_avg || exposome?.period || "2015-2022";
  }
  return String(currentYear);
}
