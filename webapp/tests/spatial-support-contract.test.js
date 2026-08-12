import test from "node:test";
import assert from "node:assert/strict";

import {
  mapSupportLabel,
  mapSupportPrefix,
  spatialSupportText,
  temporalMapLabel,
  withMapSupport,
} from "../src/utils/spatial-support.js";
import { spatialUnitLabel } from "../src/utils/spatial-unit.js";
import { vectorContourDetailIsValid } from "../src/data-repository.js";

const pm25 = {
  downloaded: {
    kind: "raster_grid",
    label: "ACAG PM2.5",
    resolution: { x: 0.01, y: 0.01, unit: "degree" },
  },
  observation: {
    kind: "raster_footprint",
    label: "ACAG PM2.5",
    resolution: { x: 0.01, y: 0.01, unit: "degree" },
  },
  analysis: {
    kind: "regular_grid",
    label: "píxel ACAG nativo",
    resolution: { x: 0.01, y: 0.01, unit: "degree" },
  },
};

test("administrative rendering never advertises the source pixel as the map", () => {
  const spatial = {
    ...pm25,
    rendered: { kind: "administrative_polygon", label: "distrito", resolution: null },
    detail: null,
  };
  assert.equal(mapSupportLabel(spatial), "distrito");
  assert.equal(mapSupportPrefix(spatial), "Mapa");
  assert.match(spatialSupportText(spatial), /^Mapa: distrito; fuente: ACAG PM2\.5/);
  assert.doesNotMatch(mapSupportLabel(spatial), /píxel|0,01/);
  assert.equal(withMapSupport({ resolution: "≈1 km" }, spatial).resolution, "distrito");
});

test("a published COG reports the rendered native support", () => {
  const spatial = {
    ...pm25,
    rendered: pm25.analysis,
    detail: { type: "cog", path: "detail/pm25.tif" },
  };
  assert.equal(mapSupportPrefix(spatial), "Celda");
  assert.match(mapSupportLabel(spatial), /píxel ACAG nativo/);
  assert.match(mapSupportLabel(spatial), /0,01 × 0,01 degree/);
});

test("verified vector contours have categorical support without invented metres", () => {
  const digest = "a".repeat(64);
  const detail = {
    type: "vector_contours",
    tiles: ["detail/noise_lden/{z}/{x}/{y}.pbf"],
    minzoom: 11,
    maxzoom: 15,
    bounds: [2, 41, 2.3, 41.6],
    source_layer: "noise_lden",
    bands: ["55-59", "60-64", "65-69", "70-74", "gt75"].map((value) => ({ value })),
    source_manifest_sha256: digest,
    source_assets: [{ path: "cataluna/barcelona.zip", sha256: digest }],
    source_sha256: digest,
    source_support_preserved: true,
    validation: {
      path: "detail/noise_lden.vector_contours.validation.json",
      sha256: digest,
    },
  };
  const spatial = {
    rendered: { kind: "vector_contours", label: "Contornos vectoriales MER/SICA", resolution: null },
    detail,
  };
  assert.equal(vectorContourDetailIsValid(detail), true);
  assert.equal(mapSupportPrefix(spatial), "Contorno");
  assert.equal(mapSupportLabel(spatial), "Contornos vectoriales MER/SICA");
  assert.doesNotMatch(spatialSupportText(spatial), /\bm\b|píxel/);
  assert.equal(vectorContourDetailIsValid({ ...detail, source_support_preserved: false }), false);
});

test("the active heat product labels ERA5-Land only in its COG year", () => {
  const spatial = {
    ...pm25,
    rendered: pm25.analysis,
    detail: {
      type: "cog",
      path: "detail/heat_summer_tmax.tif",
      temporal_support: {
        kind: "year",
        year: "2024",
        source_label: "ERA5-Land",
      },
    },
  };
  assert.equal(
    temporalMapLabel({ period: "Open-Meteo", yearLabel: "2024", detailActive: true, spatial }),
    "ERA5-Land 2024",
  );
  assert.equal(
    temporalMapLabel({ period: "Open-Meteo", yearLabel: "2023", detailActive: false, spatial }),
    "Open-Meteo 2023",
  );
});

test("TROPOMI keeps storage grid and observational footprint distinct", () => {
  const spatial = {
    downloaded: { label: "Sentinel-5P L3", resolution: { value: 1113.2, unit: "m" } },
    observation: { label: "huella TROPOMI", resolution: { x: 3500, y: 5500, unit: "m" } },
    analysis: { label: "columna S5P", resolution: { value: 1113.2, unit: "m" } },
    rendered: { kind: "cog", label: "columna S5P", resolution: { value: 1113.2, unit: "m" } },
    detail: { type: "cog", path: "detail/no2.tif" },
  };
  assert.match(spatialSupportText(spatial), /soporte observacional: huella TROPOMI/);
  assert.match(spatialSupportText(spatial), /3\.500 × 5\.500 m/);
});

test("study unit labels use real administrative names and plurals", () => {
  assert.equal(spatialUnitLabel("distrito", { plural: true }), "distritos");
  assert.equal(
    spatialUnitLabel("comuna_corregimiento", { plural: true }),
    "comunas y corregimientos",
  );
  assert.equal(spatialUnitLabel("alcaldia"), "alcaldía");
});
