import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { communeNameAtPoint, mapTooltipHtml } from "../src/utils/map-tooltip.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const css = fs.readFileSync(path.join(here, "../src/style.css"), "utf8");
const choropleth = fs.readFileSync(path.join(here, "../src/choropleth.js"), "utf8");

test("all map hovers use one tooltip with commune, value, unit and support", () => {
  const html = mapTooltipHtml({
    communeName: "Ñuñoa <centro>",
    metricLabel: "PM2.5",
    value: 20.934,
    unit: "µg/m³",
    supportLabel: "Píxel ACAG 0,01°",
  });
  assert.match(html, /Ñuñoa &lt;centro&gt;/);
  assert.match(html, /PM2\.5/);
  assert.match(html, /20\.93/);
  assert.match(html, /µg\/m³/);
  assert.match(html, /Píxel ACAG 0,01°/);
  assert.equal((choropleth.match(/mapTooltipHtml\(/g) || []).length, 1);
  assert.match(choropleth, /_showMapValuePopup\(e, \{/);
});

test("COG hover resolves the commune from the boundary layer", () => {
  const map = {
    queryRenderedFeatures(point, options) {
      assert.deepEqual(point, { x: 4, y: 9 });
      assert.deepEqual(options, { layers: ["communes-fill"] });
      return [{ properties: { name: "Providencia" } }];
    },
  };
  assert.equal(communeNameAtPoint(map, { x: 4, y: 9 }), "Providencia");
  assert.match(choropleth, /communeNameAtPoint\(_map, e\.point\)/);
});

test("vector contour hover stays categorical and uses the shared tooltip", () => {
  const html = mapTooltipHtml({
    communeName: "Eixample",
    metricLabel: "Banda Lden modelada",
    valueText: "55–59 dB(A)",
    unit: "",
    supportLabel: "Contornos vectoriales MER/SICA",
  });
  assert.match(html, /Banda Lden modelada/);
  assert.match(html, /55–59 dB\(A\)/);
  assert.doesNotMatch(html, /Sin dato/);
  assert.match(choropleth, /type:\s*"vector"/);
  assert.match(choropleth, /"source-layer": detail\.source_layer/);
  assert.match(choropleth, /Banda Lden modelada/);
  assert.match(css, /\.legend-categories\s*\{[^}]*grid-template-columns:\s*repeat\(5/s);
});

test("legend has one bounded instrument width and structured long labels", () => {
  assert.match(css, /\.legend\s*\{[^}]*width:\s*320px/s);
  assert.match(css, /max-width:\s*calc\(100vw - 32px\)/);
  assert.match(css, /\.legend-label\s*\{[^}]*-webkit-line-clamp:\s*2/s);
  assert.match(css, /width:\s*min\(320px, calc\(100vw - 16px\)\)/);
  assert.match(choropleth, /legend-metric-row/);
  assert.match(choropleth, /legend-period/);
});
