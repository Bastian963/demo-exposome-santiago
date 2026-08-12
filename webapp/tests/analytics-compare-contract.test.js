import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const panelSource = fs.readFileSync(
  path.join(here, "../src/panels/analytics-compare.js"),
  "utf8",
);
const repoSource = fs.readFileSync(path.join(here, "../src/data-repository.js"), "utf8");

test("data-repository fetches the precomputed cross-city artifact, not per-master data", () => {
  assert.match(
    repoSource,
    /loadDistributions/,
    "data-repository.js must expose loadDistributions()",
  );
  assert.match(
    repoSource,
    /v1\/analytics\/distributions\.json/,
    "loadDistributions must fetch the path written by export_webapp_distributions.py",
  );
});

test("KS max-gap marker is only drawn for exactly two selected cities", () => {
  // With >2 cities selected the pairwise gaps multiply; a single marker would
  // misleadingly imply one "the" gap. See docs/analytics_distribution_comparison.md.
  assert.match(panelSource, /cityIds\.length !== 2\) return ""/);
});

test("a degenerate (scale_undefined) MAD band is skipped, not drawn as zero-width", () => {
  assert.match(panelSource, /c\.scale_undefined\s*\n?\s*\?\s*""/);
});

test("the spatial-autocorrelation warning is wired to the fine-sample flag from the artifact", () => {
  assert.match(panelSource, /warnings\?\.includes\("spatial_autocorrelation"\)/);
});

test("the Anderson-Darling verdict distinguishes floor from ceiling capping", () => {
  // A ceiling cap (p>=0.25) means "indistinguishable" -- the OPPOSITE of a
  // floor cap (p<=0.001, "clearly different"). Collapsing them into one
  // p_capped branch prints the reverse of the truth for similar cities.
  assert.match(panelSource, /p_cap_side === "floor"/);
  assert.match(panelSource, /p_cap_side === "ceiling"/);
});

test("the exposome rail is built from the palette catalog, not a re-inferred family list", () => {
  // v3: the analytics selector mirrors the CITY_OVERVIEW picker -- same
  // getPalette().exposomes catalog, same 3 categories -- instead of inventing
  // families from column-name prefixes. See docs/analytics_distribution_comparison.md.
  assert.match(panelSource, /getPalette\(\)\?\.exposomes/);
  assert.doesNotMatch(panelSource, /FAMILY_ORDER|FAMILY_LABELS|infer_family/);
});

test("group cards (Calor/Lluvia) drill into their catalog children", () => {
  // heat_index/rain_* are palette children of the heat/rain groups; the rail
  // must collapse them under the group and resolve data to the child id.
  assert.match(panelSource, /_railGroupId/);
  assert.match(panelSource, /childIds/);
});

test("city colors are assigned by sorted slug, not catalog/array order", () => {
  // A city's color must stay stable across sessions regardless of the order
  // cities appear in catalog.json -- see feedback on stable per-city identity.
  assert.match(panelSource, /\[\.\.\.cities\.map\(\(c\) => c\.slug\)\]\.sort\(\)/);
});

test("published distributions.json keeps the artifact schema", (t) => {
  const distPath = path.join(here, "../public/data/v1/analytics/distributions.json");
  if (!fs.existsSync(distPath)) {
    t.skip("distributions.json not published locally");
    return;
  }
  const payload = JSON.parse(fs.readFileSync(distPath, "utf8"));
  assert.ok(Array.isArray(payload.cities) && payload.cities.length > 0, "cities must be a non-empty array");
  for (const city of payload.cities) {
    assert.equal(typeof city.slug, "string");
    assert.equal(typeof city.name, "string");
  }
  const indicators = payload.indicators || {};
  const indicatorIds = Object.keys(indicators);
  assert.ok(indicatorIds.length > 0, "indicators must not be empty");

  const VALID_CATEGORIES = new Set(["entorno", "sociedad", "resultados"]);
  for (const id of indicatorIds) {
    const entry = indicators[id];
    assert.ok(["fine", "admin"].includes(entry.sample_level), `${id}.sample_level invalid`);
    // Indicators are keyed by (and stamped with) their catalog exposome_id: the
    // panel matches rail cards to data by this id, never by a re-inferred family.
    assert.equal(typeof entry.exposome_id, "string", `${id}.exposome_id missing`);
    assert.equal(entry.exposome_id, id, `${id}.exposome_id must equal its key`);
    assert.ok(!("family" in entry), `${id} must not carry a legacy inferred family`);
    assert.ok(VALID_CATEGORIES.has(entry.category), `${id}.category invalid: ${entry.category}`);
    assert.ok(entry.unit === null || typeof entry.unit === "string", `${id}.unit must be string or null`);
    assert.ok(entry.column === null || typeof entry.column === "string", `${id}.column must be string or null`);
    assert.ok(Array.isArray(entry.bins) && entry.bins.length >= 2, `${id}.bins malformed`);
    assert.ok(entry.bins[0] < entry.bins[entry.bins.length - 1], `${id}.bins not increasing`);
    if (entry.log) {
      assert.ok(Array.isArray(entry.log.bins) && entry.log.bins.length >= 2, `${id}.log.bins malformed`);
      assert.ok(entry.log.bins[0] > 0, `${id}.log.bins must be strictly positive`);
      assert.ok(
        entry.log.bins[0] < entry.log.bins[entry.log.bins.length - 1],
        `${id}.log.bins not increasing`,
      );
    }
    const cities = entry.cities || {};
    assert.ok(Object.keys(cities).length > 0, `${id}.cities empty`);

    for (const [slug, c] of Object.entries(cities)) {
      assert.equal(typeof c.n, "number", `${id}.${slug}.n`);
      assert.equal(typeof c.median, "number", `${id}.${slug}.median`);
      assert.equal(typeof c.scale_undefined, "boolean", `${id}.${slug}.scale_undefined`);
      assert.ok(Array.isArray(c.hist_density), `${id}.${slug}.hist_density`);
      assert.equal(c.hist_density.length, entry.bins.length - 1, `${id}.${slug}.hist_density length`);
      assert.ok(Array.isArray(c.ecdf?.x) && Array.isArray(c.ecdf?.y), `${id}.${slug}.ecdf`);
    }

    if (entry.tests?.ks) {
      for (const pair of entry.tests.ks) {
        assert.ok(pair.d >= 0 && pair.d <= 1, `${id} KS D out of [0,1]: ${pair.d}`);
        assert.ok(pair.p >= 0 && pair.p <= 1, `${id} KS p out of [0,1]: ${pair.p}`);
      }
    }
    if (entry.tests?.ad) {
      assert.equal(typeof entry.tests.ad.p_capped, "boolean", `${id}.tests.ad.p_capped`);
      assert.ok(Number.isFinite(entry.tests.ad.a2), `${id}.tests.ad.a2 not finite`);
      // floor and ceiling caps mean opposite verdicts; the side must be explicit.
      assert.ok(
        [null, "floor", "ceiling"].includes(entry.tests.ad.p_cap_side ?? null),
        `${id}.tests.ad.p_cap_side invalid`,
      );
      assert.equal(
        entry.tests.ad.p_capped,
        entry.tests.ad.p_cap_side != null,
        `${id}.tests.ad p_capped/p_cap_side disagree`,
      );
    }
  }
});
