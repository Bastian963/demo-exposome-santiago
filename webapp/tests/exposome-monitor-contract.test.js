import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { getRendererId, valueToVisualState } from "../src/components/exposomeAnimations/scaling.js";
import { formatMeasuredValue } from "../src/utils/measurement-format.js";
import {
  isMeasuredValue,
  parkAccessState,
  percentageCellCount,
  rotorRadiansPerSecond,
  segmentedCount,
} from "../src/components/exposomeAnimations/monitorSemantics.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const palette = JSON.parse(
  fs.readFileSync(path.join(here, "../public/palette.json"), "utf8"),
);
const choroplethSource = fs.readFileSync(path.join(here, "../src/choropleth.js"), "utf8");

test("redesigned monitors declare distinct, data-honest variants", () => {
  const expected = {
    heat_hot_days: "hot_day_register",
    rain_dry_spell: "consecutive_dry_run",
    precipitation_spi: "drought_frequency",
    wind: "turbine_field",
    green: "land_cover",
    canopy: "tree_canopy",
    greenspace_access: "park_distance",
  };
  for (const [id, variant] of Object.entries(expected)) {
    assert.equal(palette.exposomes[id].chamber.variant, variant, id);
  }
  assert.match(palette.exposomes.rain_dry_spell.chamber.help, /consecutivos/i);
  assert.match(palette.exposomes.precipitation_spi.chamber.help, /no identifica meses concretos/i);
  assert.match(palette.exposomes.greenspace_access.chamber.help, /línea recta/i);
});

test("green family selects the dedicated renderer instead of PM2.5", () => {
  for (const id of ["green", "canopy", "greenspace_access"]) {
    assert.equal(getRendererId({ id, ...palette.exposomes[id] }), "green", id);
  }
});

test("temporal count encodings preserve their measured unit", () => {
  assert.equal(segmentedCount(0, { blockSize: 5, maxBlocks: 24 }), 0);
  assert.equal(segmentedCount(29.3, { blockSize: 5, maxBlocks: 24 }), 6);
  assert.equal(segmentedCount(103.75, { blockSize: 5, maxBlocks: 24 }), 21);
  assert.equal(segmentedCount(999, { blockSize: 5, maxBlocks: 24 }), 24);
  assert.equal(percentageCellCount(11.02), 11);
  assert.equal(percentageCellCount(18.64), 19);
  assert.equal(percentageCellCount(101), 100);
});

test("wind is monotonic while zero and missing remain distinct", () => {
  assert.equal(rotorRadiansPerSecond(null, 0.8), 0);
  assert.equal(rotorRadiansPerSecond(0, 0.8), 0);
  assert.ok(rotorRadiansPerSecond(1.2, 0.1) > 0);
  assert.ok(rotorRadiansPerSecond(4.6, 0.9) > rotorRadiansPerSecond(1.2, 0.1));
  assert.equal(isMeasuredValue(NaN), false);
});

test("COG hover previews the monitor and restores the selected commune on leave", () => {
  const hoverStart = choroplethSource.indexOf("async function _handleCogMouseMove");
  const leaveStart = choroplethSource.indexOf("function _handleCogMouseLeave", hoverStart);
  const detailStart = choroplethSource.indexOf("function _installSubcomunaSource", leaveStart);
  assert.ok(hoverStart >= 0 && leaveStart > hoverStart && detailStart > leaveStart);

  const hoverHandler = choroplethSource.slice(hoverStart, leaveStart);
  const leaveHandler = choroplethSource.slice(leaveStart, detailStart);
  assert.match(hoverHandler, /m\.previewValue\(value, \{/);
  assert.match(hoverHandler, /domain: \{/);
  assert.match(hoverHandler, /unit,/);
  assert.match(hoverHandler, /metricLabel,/);
  assert.match(leaveHandler, /_restoreSelectedContext\(\)/);
});

test("aggregate and fine-GeoJSON hover restore the same selected context", () => {
  const communeLeave = choroplethSource.slice(
    choroplethSource.indexOf("function _handleCommuneMouseLeave"),
    choroplethSource.indexOf("function _handleSubcomunaMouseMove"),
  );
  const subcomunaLeave = choroplethSource.slice(
    choroplethSource.indexOf("function _handleSubcomunaMouseLeave"),
    choroplethSource.indexOf("function _clearSubcomunaHoverState"),
  );
  assert.match(communeLeave, /_restoreSelectedContext\(\)/);
  assert.match(subcomunaLeave, /_restoreSelectedContext\(\)/);
});

test("COG detail uses its colour domain for monitor intensity", () => {
  const hoverStart = choroplethSource.indexOf("async function _handleCogMouseMove");
  const leaveStart = choroplethSource.indexOf("function _handleCogMouseLeave", hoverStart);
  const hoverHandler = choroplethSource.slice(hoverStart, leaveStart);
  assert.match(hoverHandler, /min: range\.min/);
  assert.match(hoverHandler, /max: range\.max/);

  const cogDomain = { min: 0, max: 2.5726271134821106, p5: 0, p95: 2.5726271134821106, n: 1 };
  const state = valueToVisualState(0.8316, { id: "wind", chamber: {} }, cogDomain);
  assert.ok(state.intensity > 0.3 && state.intensity < 0.34);
  assert.equal(state.visualCount, 32);
});

test("preview context restores the commune value, domain and unit", async () => {
  globalThis.document = globalThis.document || {
    getElementById: () => null,
    querySelector: () => null,
  };
  const monitor = await import("../src/components/exposomeAnimations/index.js");
  monitor._resetForTests();
  monitor.setChamberCopy({
    id: "no2",
    label: "NO₂",
    unit: "µg/m³",
    chamber: { mode: "traffic", value_label: "NO₂:", unit: "µg/m³" },
  });
  const communeDomain = { min: 10, max: 30, p5: 10, p95: 30, n: 52 };
  const rasterDomain = { min: 1e-5, max: 5e-5, p5: 1e-5, p95: 5e-5, n: 1 };
  monitor.setStudyDomain(communeDomain);
  monitor.setValue(20);
  monitor.previewValue(3e-5, {
    domain: rasterDomain,
    unit: "mol/m²",
    metricLabel: "NO₂ columna troposférica",
  });
  let state = monitor._getStateForTests();
  assert.equal(state.previewValue, 3e-5);
  assert.deepEqual(state.effectiveDomain, rasterDomain);
  assert.equal(state.previewContext.unit, "mol/m²");

  monitor.clearPreviewValue();
  state = monitor._getStateForTests();
  assert.equal(state.previewValue, null);
  assert.equal(state.baseValue, 20);
  assert.deepEqual(state.effectiveDomain, communeDomain);
  monitor._resetForTests();
});

test("popup, pixel indicator and monitor share a nonzero small-value format", () => {
  assert.equal(formatMeasuredValue(0.000009102), "9.102e-6");
  assert.equal(formatMeasuredValue(20.934), "20.93");
  assert.match(choroplethSource, /formatMeasuredValue\(value\)/);
});

test("park access keeps unavailable and no-mapped-park states separate", () => {
  assert.deepEqual(parkAccessState(null, 0.5), { status: "unavailable", distanceT: 0 });
  assert.deepEqual(parkAccessState(99999, 0.5), { status: "no_park_mapped", distanceT: 1 });
  assert.deepEqual(parkAccessState(120, 0.25), { status: "available", distanceT: 0.25 });
});

test("panel counters name the same unit drawn by the redesigned monitors", () => {
  const studyDomain = { min: 0, max: 100, p5: 0, p95: 100, n: 16 };
  assert.equal(valueToVisualState(91, { id: "heat_hot_days", chamber: {} }, studyDomain).visualCount, 19);
  assert.equal(valueToVisualState(91, { id: "rain_dry_spell", chamber: {} }, studyDomain).visualCount, 19);
  assert.equal(valueToVisualState(18.64, { id: "precipitation_spi", chamber: {} }, studyDomain).visualCount, 19);
  assert.equal(valueToVisualState(0.9, { id: "canopy", chamber: {} }, studyDomain).visualCount, 1);
  assert.equal(valueToVisualState(99999, { id: "greenspace_access", chamber: {} }, studyDomain).visualCount, 0);
  assert.equal(valueToVisualState(50, { id: "wind", chamber: {} }, studyDomain).visualCount, 50);
  assert.equal(valueToVisualState(91, { chamber: { variant: "hot_day_register" } }, studyDomain).visualCount, 19);
});
