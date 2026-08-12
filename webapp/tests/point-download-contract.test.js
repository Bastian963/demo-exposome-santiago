// Contracts for the point-download panel.
//
// The panel touches the DOM and the COG reader, so it cannot be imported under
// `node --test`. Asserted by reading the source, in the house style, for the
// invariants that would silently produce a dishonest number if they regressed.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const read = (relative) => fs.readFileSync(path.join(HERE, relative), "utf8");

const panel = read("../src/panels/point-download.js");
const main = read("../src/main.js");
const latam = read("../src/states/latam.js");
const styles = read("../src/style.css");
const html = read("../index.html");

test("the panel container exists and starts hidden", () => {
  assert.match(html, /id="pointDownloadPanel"[^>]*class="point-download-panel"/);
  assert.match(html, /id="pointDownloadPanel"[^>]*hidden/);
});

test("the panel exports the init/show/hide/isVisible quartet", () => {
  for (const name of [
    "initPointDownloadPanel",
    "showPointDownloadPanel",
    "hidePointDownloadPanel",
    "isPointDownloadPanelVisible",
  ]) {
    assert.match(panel, new RegExp(`export (async )?function ${name}\\b`), name);
  }
});

test("it owns a body mode class so it does not inherit stale chrome", () => {
  // The legend, time-slider and year-tabs are shown/hidden purely off
  // latam-mode / city-mode / commune-mode.
  assert.match(panel, /classList\.add\("download-mode"\)/);
  assert.match(panel, /classList\.remove\("download-mode"\)/);
  assert.match(styles, /body\.download-mode .*\.time-slider-bar/s);
  assert.match(styles, /body\.download-mode .*\.year-tabs-bar/s);
});

test("all four registration sites exist, or the deep link silently no-ops", () => {
  assert.match(main, /DOWNLOAD: "download"/);
  assert.match(main, /_appState\.view === STATE\.DOWNLOAD/); // deep link on load
  assert.match(main, /newState\.view === STATE\.DOWNLOAD/); // popstate
  const hideCalls = main.match(/hidePointDownloadPanelIfOpen\(\)/g) || [];
  // once per navigation away (city + commune) plus the popstate guard
  assert.ok(hideCalls.length >= 3, `expected >=3 hide call sites, got ${hideCalls.length}`);
  assert.match(latam, /_onOpenDownload/);
});

test("hidden studies are never resolution targets", () => {
  // buenos_aires_comunas is hidden and has a smaller bbox than
  // buenos_aires_amba; including it would route a CABA address to the study
  // with no detail COGs purely because its box is smaller.
  assert.match(panel, /!study\.hidden/);
});

test("availability comes from the manifest, never from palette flags", () => {
  assert.match(panel, /unavailableReason\(manifest, indicatorId\)/);
  assert.ok(
    !/has_fine_layer/.test(panel),
    "has_fine_layer is wrong in both directions; the manifest is the authority",
  );
});

test("administrative values carry no radius and are never blended", () => {
  const admin = panel.split("function administrativeRow")[1] || "";
  assert.match(admin, /radius_m: null/);
  assert.match(admin, /radius_status: "not_applicable"/);
  assert.match(admin, /units_touched|spatial_id/);
});

test("the browser emits the containing cell only, never a fake buffer", () => {
  // It reads a single native pixel. Emitting radius_m: 300 next to a
  // single-pixel value would imply an average that was never taken; the
  // area-weighted disc is the CLI's job.
  const raster = panel.split("estimand_kind: \"raster_block\"")[1] || "";
  assert.match(raster, /radius_m: 0/);
  assert.match(raster, /sd_within_buffer: null/);
  assert.ok(
    !/for \(const radius of _radii\)[\s\S]{0,400}value: sample\.value/.test(panel),
    "must not emit one row per radius from a single pixel read",
  );
});

test("the panel never passes a zoom into the COG read", () => {
  assert.ok(!/getZoom/.test(panel), "the download path must not read map zoom");
  assert.match(panel, /sampleIndicatorsAtPoint/);
});

test("pasted input is escaped everywhere it is rendered", () => {
  assert.match(panel, /function escHtml/);
  // The raw line and the geographic note are the two user-influenced strings.
  assert.match(panel, /escHtml\(entry\.raw\)/);
  assert.match(panel, /escHtml\(row\.query_id\)/);
});

test("the postal field explains itself per country instead of failing blankly", () => {
  assert.match(panel, /POSTAL_GEOGRAPHY_NOTE/);
  for (const country of ["CL", "MX", "BR", "AR", "PE", "CO", "ES"]) {
    assert.match(panel, new RegExp(`${country}:`), `note for ${country}`);
  }
});

test("it offers the CLI command for the buffer radii it cannot compute", () => {
  assert.match(panel, /exposome extract-points/);
  assert.match(panel, /--radii/);
});
