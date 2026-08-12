// Pure-function contracts for the download tab's input handling.
// These mirror tests/test_geocoding.py so the two implementations cannot drift.
import test from "node:test";
import assert from "node:assert/strict";

import {
  KIND_ADDRESS,
  KIND_EMPTY,
  KIND_LATLON,
  KIND_POSTAL,
  classifyInput,
  classifyLines,
  normalizePostal,
  parseLatLon,
  summarizeKinds,
} from "../src/utils/point-input.js";
import { parseCSV, parseCSVObjects, serializeCSV } from "../src/utils/csv.js";
import {
  featureContainsPoint,
  findFeatureAtPoint,
  geometryContainsPoint,
  unitsNearby,
} from "../src/utils/geometry.js";

const MAIPU = "Manuel Rodriguez 1085, Maipu, Santiago, Chile";

test("an address is the default classification", () => {
  assert.equal(classifyInput(MAIPU).kind, KIND_ADDRESS);
});

test("lat,lon parses and keeps the map-app order", () => {
  const result = classifyInput("-33.45, -70.65");
  assert.equal(result.kind, KIND_LATLON);
  assert.equal(result.lat, -33.45);
  assert.equal(result.lon, -70.65);
});

test("whitespace separates coordinates too", () => {
  assert.equal(classifyInput("-33.45 -70.65").kind, KIND_LATLON);
});

test("out-of-range pairs are not coordinates", () => {
  const result = classifyInput("999.0, 999.0");
  assert.equal(result.kind, KIND_ADDRESS);
  assert.ok(result.note);
});

test("blank lines classify as empty", () => {
  assert.equal(classifyInput("   ").kind, KIND_EMPTY);
});

test("a bare five-digit code is ambiguous until a country is declared", () => {
  // MX, ES and PE all use five digits.
  assert.equal(classifyInput("06700").kind, KIND_ADDRESS);
  assert.equal(classifyInput("06700", "MX").kind, KIND_POSTAL);
});

test("an inline country prefix declares the postal country", () => {
  const result = classifyInput("MX 06700");
  assert.equal(result.kind, KIND_POSTAL);
  assert.equal(result.country, "MX");
  assert.equal(result.postalCode, "06700");
});

test("chilean seven-digit and argentine CPA shapes", () => {
  assert.equal(classifyInput("CL 7500000").postalCode, "7500000");
  assert.equal(classifyInput("AR C1425DKE").postalCode, "C1425DKE");
});

test("brazilian CEP with or without the dash", () => {
  for (const code of ["01310-100", "01310100"]) {
    assert.equal(classifyInput(`BR ${code}`).kind, KIND_POSTAL, code);
  }
});

test("a wrong shape for the country is not silently a postal code", () => {
  assert.equal(classifyInput("12345", "CL").kind, KIND_ADDRESS);
});

test("normalizePostal rejects unknown countries", () => {
  assert.equal(normalizePostal("ZZ", "1234"), null);
});

test("parseLatLon returns null for text", () => {
  assert.equal(parseLatLon(MAIPU), null);
});

test("classifyLines numbers rows and drops blanks", () => {
  const rows = classifyLines(`-33.45, -70.65\n\nCL 7500000\n${MAIPU}\n`);
  assert.equal(rows.length, 3);
  assert.equal(rows[0].queryId, "point_0001");
  assert.deepEqual(rows.map((r) => r.kind), [KIND_LATLON, KIND_POSTAL, KIND_ADDRESS]);
});

test("summarizeKinds counts each kind", () => {
  const counts = summarizeKinds(classifyLines(`-33.45,-70.65\n${MAIPU}`));
  assert.equal(counts[KIND_LATLON], 1);
  assert.equal(counts[KIND_ADDRESS], 1);
});

// --- CSV -------------------------------------------------------------------

test("quoted commas survive the round trip", () => {
  const text = 'id,address\n1,"Manuel Rodriguez 1085, Maipu"\n';
  const rows = parseCSVObjects(text);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].address, "Manuel Rodriguez 1085, Maipu");
});

test("escaped quotes and CRLF", () => {
  const rows = parseCSV('a,b\r\n"say ""hi""",2\r\n');
  assert.deepEqual(rows[1], ['say "hi"', "2"]);
});

test("a BOM does not corrupt the first header", () => {
  const rows = parseCSVObjects("﻿id,lon\n1,-70.6\n");
  assert.deepEqual(Object.keys(rows[0]), ["id", "lon"]);
});

test("embedded newlines stay inside their field", () => {
  const rows = parseCSV('a\n"line1\nline2"\n');
  assert.equal(rows[1][0], "line1\nline2");
});

test("serializeCSV quotes what needs quoting", () => {
  const text = serializeCSV([{ id: 1, note: 'a,b "c"' }]);
  assert.equal(text, 'id,note\n1,"a,b ""c"""');
});

test("serialize then parse is a round trip", () => {
  const records = [{ id: "1", address: "Av. Siempre Viva 742, Springfield" }];
  assert.deepEqual(parseCSVObjects(serializeCSV(records)), records);
});

// --- geometry --------------------------------------------------------------

const SQUARE_WITH_HOLE = {
  type: "Polygon",
  coordinates: [
    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
    [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
  ],
};

test("a point in a hole is outside the polygon", () => {
  assert.equal(geometryContainsPoint(SQUARE_WITH_HOLE, 1, 1), true);
  assert.equal(geometryContainsPoint(SQUARE_WITH_HOLE, 5, 5), false);
  assert.equal(geometryContainsPoint(SQUARE_WITH_HOLE, 20, 20), false);
});

test("featureContainsPoint caches a bbox on the feature", () => {
  const feature = { geometry: SQUARE_WITH_HOLE };
  assert.equal(featureContainsPoint(feature, 1, 1), true);
  assert.deepEqual(feature._bbox, [0, 0, 10, 10]);
});

test("findFeatureAtPoint returns the containing feature", () => {
  const features = [
    { id: "a", geometry: SQUARE_WITH_HOLE },
    {
      id: "b",
      geometry: { type: "Polygon", coordinates: [[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]] },
    },
  ];
  assert.equal(findFeatureAtPoint(features, 25, 25).id, "b");
  assert.equal(findFeatureAtPoint(features, 100, 100), null);
});

test("unitsNearby is a bbox-level diagnostic, not a blend", () => {
  const features = [
    { geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] } },
    { geometry: { type: "Polygon", coordinates: [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]] } },
  ];
  // A point right on the shared edge touches both units.
  assert.equal(unitsNearby(features, 1.0, 0.5, 1000), 2);
  assert.equal(unitsNearby(features, 1.0, 0.5, 0), 0);
});
