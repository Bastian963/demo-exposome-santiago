import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolveExposomeDefinition } from "../src/utils/exposome-definition.js";
import { getRendererId } from "../src/components/exposomeAnimations/scaling.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const palette = JSON.parse(
  fs.readFileSync(path.join(here, "../public/palette.json"), "utf8"),
);

test("temporal override is the column consumed by the map", () => {
  const expo = palette.exposomes.community_safety_property;
  const resolved = resolveExposomeDefinition("community_safety_property", expo, {
    column: expo.year_columns["2020"],
    yearLabel: "2020",
  });
  assert.equal(resolved.column, "crime_property_rate_100k_2020");
  assert.equal(resolved.yearLabel, "2020");
});

test("outcomes stay outside exposome categories and use dedicated assets", () => {
  for (const id of ["suicide_mortality", "road_traffic_mortality"]) {
    const outcome = palette.exposomes[id];
    assert.equal(outcome.category, "resultados");
    assert.match(outcome.data_asset, /^outcomes\//);
    assert.equal(getRendererId({ id, ...outcome }), "outcome");
  }
});

test("registered safety uses a dedicated renderer", () => {
  const safety = palette.exposomes.community_safety_property;
  assert.equal(getRendererId({ id: "community_safety_property", ...safety }), "safety");
});
