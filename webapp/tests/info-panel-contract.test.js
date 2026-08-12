import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const mainSource = fs.readFileSync(path.join(here, "../src/main.js"), "utf8");

// Fields the FUENTE/ESPECIFICACIONES tabs require on every sources entry;
// scripts/validate_webapp_info.py enforces the same contract on bundles.
const REQUIRED_SOURCE_FIELDS = [
  "name",
  "url",
  "license",
  "spatial_resolution",
  "temporal_coverage",
  "validation",
];

test("CITACION prefers the curated registry BibTeX over the client fallback", () => {
  assert.match(
    mainSource,
    /const bibtex = src\.bibtex \|\| \(doi/,
    "main.js must render src.bibtex when the bundle provides one",
  );
});

test("published santiago sources.json keeps the canonical schema", (t) => {
  const sourcesPath = path.join(
    here,
    "../public/data/v1/cl/santiago/santiago_communes/sources.json",
  );
  if (!fs.existsSync(sourcesPath)) {
    t.skip("santiago bundle not published locally");
    return;
  }
  const payload = JSON.parse(fs.readFileSync(sourcesPath, "utf8"));
  const sources = payload.sources || payload;
  const entries = Object.entries(sources);
  assert.ok(entries.length > 0, "sources.json must not be empty");
  for (const [key, entry] of entries) {
    for (const field of REQUIRED_SOURCE_FIELDS) {
      assert.equal(
        typeof entry[field],
        "string",
        `${key}.${field} must be a string`,
      );
    }
    assert.ok(
      !entry.name.startsWith("{"),
      `${key}.name looks like a stringified dict: ${entry.name.slice(0, 40)}`,
    );
  }
});
