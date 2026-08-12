// The download path must never let viewport zoom decide which overview it
// reads. Enforced by reading the source, in the house style, because the call
// itself needs a network COG.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  deliveredSupportM,
  detailAssetFor,
  effectiveSupportM,
  emitsWithinBufferSd,
  radiusStatus,
  sourceNativeResolutionM,
  unavailableReason,
} from "../src/utils/detail-asset.js";
// Pure helpers only; the module's geotiff import is fine under node --test.
import { pixelIndex, toWebMercator } from "../src/utils/cog-sample.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(HERE, "../src/utils/cog-sample.js"), "utf8");

test("the download path reads the native pixel, not the tile pyramid", () => {
  // locationValues() maps onto the XYZ tile grid and CogReader synthesises
  // those tiles from the COG, so its value is resampled. Measured on the
  // published bundle: Lima PM2.5 reads 23.435 through tiles and 23.038 from
  // the native grid — a different cell. A download must return the published
  // value, so this path goes to geotiff directly.
  // Checked on imports, not on any mention: the comment above explains why the
  // tile reader is unsuitable and naturally names it.
  const imports = source.match(/^import .*$/gm) || [];
  assert.ok(
    !imports.some((line) => /maplibre-cog-protocol|locationValues/.test(line)),
    "must not import the tile-grid reader for downloads",
  );
  assert.match(source, /from "geotiff"/);
  assert.match(source, /readRasters/);
  assert.ok(!/getZoom/.test(source), "the download path must not read map zoom");
});

test("web mercator forward transform is exact at the origin and symmetric", () => {
  const [x0, y0] = toWebMercator(0, 0);
  assert.ok(Math.abs(x0) < 1e-9 && Math.abs(y0) < 1e-9);
  const [xa, ya] = toWebMercator(-70.65, -33.45);
  const [xb, yb] = toWebMercator(70.65, 33.45);
  assert.ok(Math.abs(xa + xb) < 1e-6);
  assert.ok(Math.abs(ya + yb) < 1e-6);
  // Cross-checked against pyproj EPSG:4326 -> EPSG:3857 for Santiago and Lima.
  assert.ok(Math.abs(xa - -7864722.0245) < 0.01, `Santiago x: ${xa}`);
  assert.ok(Math.abs(ya - -3955187.3994) < 0.01, `Santiago y: ${ya}`);
  const [xl, yl] = toWebMercator(-77.03, -12.05);
  assert.ok(Math.abs(xl - -8574940.3758) < 0.01, `Lima x: ${xl}`);
  assert.ok(Math.abs(yl - -1351399.2587) < 0.01, `Lima y: ${yl}`);
});

test("pixelIndex floors into the grid and rejects points outside it", () => {
  const grid = { originX: 0, originY: 1000, resX: 100, resY: -100, width: 10, height: 10 };
  assert.deepEqual(pixelIndex(grid, 50, 950), { col: 0, row: 0 });
  assert.deepEqual(pixelIndex(grid, 999, 1), { col: 9, row: 9 });
  assert.equal(pixelIndex(grid, -1, 950), null);
  assert.equal(pixelIndex(grid, 50, 1001), null);
  assert.equal(pixelIndex(grid, 1001, 950), null);
});

test("the JS gate matches the python fixture case for case", () => {
  // Generated from src/exposome/point_support.py, the canonical implementation.
  // tests/test_point_support.py asserts Python still matches it; this asserts
  // the browser mirror does too, so a pasted address cannot get one answer in
  // the tab and another from the CLI.
  const fixturePath = path.join(HERE, "../../tests/fixtures/point_support_parity.json");
  const { cases } = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  assert.ok(cases.length > 0);
  for (const item of cases) {
    const label = `${item.indicator} @ ${item.radius_m}m`;
    // Recomputed from the raw declarations, not taken from the fixture: this is
    // what proves the JS applies max(observation, analysis) like Python does.
    const support = effectiveSupportM(item.record);
    assert.equal(support, item.effective_support_m, `support for ${label}`);
    assert.equal(radiusStatus(support, item.radius_m), item.radius_status, label);
    assert.equal(deliveredSupportM(support, item.radius_m),
      item.delivered_support_m, label);
    assert.equal(emitsWithinBufferSd(support, item.radius_m), item.emits_sd, label);
  }
});

test("effective support is the coarsest of observation and analysis", () => {
  // The two cases a naive gate gets wrong in opposite directions.
  const no2 = {
    observation: { resolution: { x: 3500, y: 5500, y_max: 7000, unit: "m" } },
    analysis: { resolution: { value: 1113.2, unit: "m" } },
  };
  const canopy = {
    observation: { resolution: { value: 1, unit: "m" } },
    analysis: { resolution: { value: 30, unit: "m" } },
  };
  assert.equal(effectiveSupportM(no2), 7000);
  assert.equal(effectiveSupportM(canopy), 30);
  // A degree grid converts with the repo's own constant: 0.01 deg = 1113.2 m.
  const degrees = effectiveSupportM({
    analysis: { resolution: { x: 0.01, y: 0.01, unit: "degree" } },
  });
  assert.ok(Math.abs(degrees - 1113.2) < 1e-6, `expected ~1113.2, got ${degrees}`);
});

test("source_native_resolution_m is reported, never used as the support", () => {
  // The manifest says 1.0 for canopy (the source height raster) while the
  // published product is a 30 m fraction.
  assert.equal(sourceNativeResolutionM({ source_native_resolution_m: 1.0 }), 1.0);
  assert.equal(
    effectiveSupportM({ analysis: { resolution: { value: 30, unit: "m" } } }),
    30,
  );
});

test("the radius gate mirrors the python one", () => {
  // NO2: 7000 m observation footprint, so no offered radius resolves.
  for (const radius of [0, 300, 500, 1000]) {
    assert.equal(radiusStatus(7000, radius), "sub_observation", `no2 @ ${radius}`);
  }
  // alan 463.83 m resolves from 300 m; pm25 1113.2 m needs a kilometre.
  assert.equal(radiusStatus(463.83, 300), "resolved");
  assert.equal(radiusStatus(1113.2, 500), "sub_observation");
  assert.equal(radiusStatus(1113.2, 1000), "resolved");
  // canopy is published at 30 m, not the 1 m of the source height raster.
  assert.equal(radiusStatus(30, 300), "resolved");
});

test("delivered support is never finer than the product", () => {
  assert.equal(deliveredSupportM(11132, 300), 11132);
  assert.equal(deliveredSupportM(463.83, 1000), 2000);
});

test("within-buffer sd is suppressed unless the radius resolves", () => {
  assert.equal(emitsWithinBufferSd(7000, 1000), false);
  assert.equal(emitsWithinBufferSd(30, 300), true);
});

test("detailAssetFor reads the manifest, not palette flags", () => {
  const manifest = {
    spatial_indicators: { pm25: { detail: { type: "cog", path: "detail/pm25.tif" } } },
    temporal_indicators: {
      pm25: { years: { 2020: { detail: { type: "cog", path: "annual/detail/pm25_2020.tif" } } } },
    },
  };
  assert.equal(detailAssetFor(manifest, "pm25").path, "detail/pm25.tif");
  assert.equal(detailAssetFor(manifest, "pm25", 2020).path, "annual/detail/pm25_2020.tif");
  assert.equal(detailAssetFor(manifest, "no2"), null);
});

test("green's detail is a geojson, so it is not a COG", () => {
  const manifest = {
    spatial_indicators: { green: { detail: { type: "geojson", path: "subcomuna/green.geojson" } } },
  };
  assert.equal(detailAssetFor(manifest, "green").type, "geojson");
});

test("unavailableReason surfaces the study's own declaration", () => {
  const manifest = {
    spatial_indicators: {
      pm25: { availability: { status: "available", reason: null } },
      nse: { availability: { status: "unavailable", reason: "country_not_supported" } },
    },
  };
  assert.equal(unavailableReason(manifest, "pm25"), null);
  assert.equal(unavailableReason(manifest, "nse"), "country_not_supported");
  assert.equal(unavailableReason(manifest, "absent"), "not_published_by_study");
});

test("the Mercator storage grid is never read as ground metres", () => {
  // Santiago PM2.5 stores 1192.4 Mercator units for a 1113.0 m product; a
  // Mercator metre is cos(latitude) ground metres, so reading storage as ground
  // truth overstates resolution by ~10%.
  const asset = {
    source_native_resolution_m: 1113.0,
    storage_grid: { resolution: { x: 1192.4492438629352, y: 1192.4492438629352, unit: "m" } },
  };
  assert.equal(sourceNativeResolutionM(asset), 1113.0);
  assert.equal(sourceNativeResolutionM({ storage_grid: { resolution: { x: 1192.4 } } }), null);
  assert.ok(
    !/storage_grid/.test(
      fs.readFileSync(path.join(HERE, "../src/utils/detail-asset.js"), "utf8")
        .split("export function effectiveSupportM")[1] || "",
    ),
    "effectiveSupportM must not read storage_grid",
  );
});
