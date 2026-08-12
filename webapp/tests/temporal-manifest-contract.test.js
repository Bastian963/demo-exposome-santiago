import test from "node:test";
import assert from "node:assert/strict";

import {
  resetStudyRepository,
  selectStudy,
  studyAnnualYears,
  studyTemporalIndicator,
  studyTemporalYear,
  studySpatialIndicator,
  studyHasFineLayer,
  detailSupportsYear,
} from "../src/data-repository.js";
import { joinAnnualRecords } from "../src/utils/temporal-data.js";

test("study manifest is authoritative for temporal years and assets", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "lima_distritos", available: true, bundle: "v1/pe/lima/lima_distritos" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "lima_distritos",
      temporal_indicators: {
        wind: {
          layer_id: "wind",
          value_column: "wind_speed_mean",
          years: {
            "2023": { asset: { path: "annual/wind_2023.json" } },
            "2024": { asset: { path: "annual/wind_2024.json" } },
          },
        },
      },
    }));
  };
  try {
    await selectStudy("lima_distritos");
    assert.deepEqual(studyAnnualYears("wind"), ["2023", "2024"]);
    assert.equal(studyTemporalIndicator("wind").value_column, "wind_speed_mean");
    assert.equal(studyTemporalYear("wind", 2024).asset.path, "annual/wind_2024.json");
    assert.deepEqual(studyAnnualYears("pm25"), []);
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});

test("tabular annual records join onto master geometry by spatial_id", () => {
  const master = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", geometry: { type: "Point", coordinates: [0, 0] }, properties: { spatial_id: "a", name: "A" } },
      { type: "Feature", geometry: { type: "Point", coordinates: [1, 1] }, properties: { spatial_id: "b", name: "B" } },
    ],
  };
  const joined = joinAnnualRecords(master, {
    records: [
      { spatial_id: "a", year: 2024, wind_speed_mean: 1.5 },
      { spatial_id: "b", year: 2024, wind_speed_mean: 2.5 },
    ],
  });
  assert.equal(joined.features[0].properties.wind_speed_mean, 1.5);
  assert.deepEqual(joined.features[1].geometry.coordinates, [1, 1]);
});

test("schema v3 hides a COG that lacks canonical scale verification", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "stale", available: true, bundle: "v1/stale" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "stale",
      spatial: { unit_type: "comuna_corregimiento" },
      spatial_indicators: {
        pm25: {
          rendered: { kind: "cog", label: "píxel ACAG", resolution: { value: 1113, unit: "m" } },
          detail: { type: "cog", path: "detail/pm25.tif" },
        },
      },
    }));
  };
  try {
    await selectStudy("stale");
    const spatial = studySpatialIndicator("pm25");
    assert.equal(spatial.detail, null);
    assert.equal(spatial.rendered.kind, "administrative_polygon");
    assert.equal(spatial.rendered.label, "comuna o corregimiento");
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});

test("a year-scoped heat COG is active only for its ERA5-Land year", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "santiago", available: true, bundle: "v1/santiago" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "santiago",
      spatial: { unit_type: "commune" },
      spatial_indicators: {
        heat_summer_tmax: {
          boundary_role: "mask_only",
          rendered: { kind: "cog", label: "Tmax ERA5-Land", resolution: { value: 11132, unit: "m" } },
          detail: {
            type: "cog",
            path: "detail/heat_summer_tmax.tif",
            canonical_resolution_verified: true,
            temporal_support: {
              kind: "year",
              year: "2024",
              source_label: "ERA5-Land",
            },
          },
        },
      },
    }));
  };
  try {
    await selectStudy("santiago");
    assert.equal(detailSupportsYear(
      { temporal_support: { kind: "year", year: "2024" } },
      2024,
    ), true);
    assert.equal(studyHasFineLayer("heat_summer_tmax", { year: "2024" }), true);
    assert.equal(
      studySpatialIndicator("heat_summer_tmax", { year: "2024" }).rendered.kind,
      "cog",
    );
    const earlier = studySpatialIndicator("heat_summer_tmax", { year: "2023" });
    assert.equal(studyHasFineLayer("heat_summer_tmax", { year: "2023" }), false);
    assert.equal(earlier.detail, null);
    assert.equal(earlier.rendered.kind, "administrative_polygon");
    assert.equal(earlier.rendered.label, "comuna");
    assert.equal(earlier.boundary_role, "analysis_unit");
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});

test("annual PM2.5 uses its matching COG and never reuses the chronic base COG", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "santiago", available: true, bundle: "v1/santiago" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "santiago",
      spatial: { unit_type: "commune" },
      temporal_indicators: {
        pm25: {
          color_domain: { min: 10, max: 35 },
          years: {
            "2015": {
              asset: { path: "annual/pm25_2015.json" },
              detail: {
                type: "cog",
                path: "annual/detail/pm25_2015.tif",
                canonical_resolution_verified: true,
                source_support_preserved: true,
                color_domain: { min: 11, max: 30 },
                temporal_support: {
                  kind: "year",
                  year: "2015",
                  source_label: "ACAG V6.GL.02",
                },
              },
            },
            "2016": { asset: { path: "annual/pm25_2016.json" } },
          },
        },
      },
      spatial_indicators: {
        pm25: {
          boundary_role: "mask_only",
          rendered: { kind: "cog", label: "píxel ACAG", resolution: { x: 0.01, y: 0.01, unit: "degree" } },
          detail: {
            type: "cog",
            path: "detail/pm25.tif",
            canonical_resolution_verified: true,
            color_domain: { min: 14, max: 27 },
            temporal_support: {
              kind: "period",
              start_year: "2015",
              end_year: "2022",
              aggregation: "mean",
              source_label: "ACAG V6.GL.02",
            },
          },
        },
      },
    }));
  };
  try {
    await selectStudy("santiago");
    const annual2015 = studySpatialIndicator("pm25", { year: "2015" });
    assert.equal(annual2015.detail.path, "annual/detail/pm25_2015.tif");
    assert.deepEqual(annual2015.detail.color_domain, { min: 10, max: 35 });
    const annual2016 = studySpatialIndicator("pm25", { year: "2016" });
    assert.equal(annual2016.detail, null);
    assert.equal(annual2016.rendered.kind, "administrative_polygon");
    const base = studySpatialIndicator("pm25");
    assert.equal(base.detail.path, "detail/pm25.tif");
    assert.deepEqual(base.detail.color_domain, { min: 10, max: 35 });
    assert.equal(detailSupportsYear(base.detail), true);
    assert.equal(detailSupportsYear(base.detail, "2015"), false);
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});

test("required annual spatial series is atomic and never exposes commune fallback years", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "santiago", available: true, bundle: "v1/santiago" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "santiago",
      spatial: { unit_type: "commune" },
      temporal_indicators: {
        alan: {
          expected_years: ["2023", "2024"],
          years: {
            "2023": {
              asset: { path: "annual/alan_2023.json" },
              detail: {
                type: "cog",
                path: "annual/detail/alan_2023.tif",
                canonical_resolution_verified: true,
                source_support_preserved: true,
                source_native_resolution_m: 463.83,
                temporal_support: { kind: "year", year: "2023", source_label: "VIIRS" },
              },
            },
            "2024": { asset: { path: "annual/alan_2024.json" } },
          },
        },
      },
      spatial_indicators: {
        alan: {
          boundary_role: "mask_only",
          publication_target: { kind: "native_raster", required_for_production: true },
          rendered: { kind: "cog", label: "VIIRS", resolution: { value: 463.83, unit: "m" } },
          detail: { type: "cog", path: "detail/alan.tif", canonical_resolution_verified: true },
        },
      },
    }));
  };
  try {
    await selectStudy("santiago");
    assert.deepEqual(studyAnnualYears("alan"), []);
    const missing = studySpatialIndicator("alan", { year: "2024" });
    assert.equal(missing.detail, null);
    assert.equal(missing.rendered.kind, "unavailable");
    assert.equal(missing.temporal_unavailable, true);
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});

test("annual analysis-grid harvest keeps its year-specific GeoJSON", async () => {
  resetStudyRepository();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/catalog.json")) {
      return new Response(JSON.stringify({
        studies: [{ study_id: "lima", available: true, bundle: "v1/lima" }],
      }));
    }
    return new Response(JSON.stringify({
      schema_version: 3,
      study_id: "lima",
      temporal_indicators: {
        green: {
          expected_years: ["2024"],
          color_domain: { min: 0, max: 80 },
          spatial_target: { kind: "analysis_grid", required_for_production: true },
          years: {
            "2024": {
              asset: { path: "annual/greenspace_multisource_2024.json" },
              detail: {
                type: "geojson",
                path: "annual/detail/green_2024.geojson",
                analysis_grid_verified: true,
                grid_alignment: "study_aoi_metric_grid",
                source_support_preserved: true,
                analysis_resolution_m: 1000,
                temporal_support: { kind: "year", year: "2024", source_label: "Dynamic World" },
              },
            },
          },
        },
      },
      spatial_indicators: { green: { rendered: { kind: "geojson" }, detail: null } },
    }));
  };
  try {
    await selectStudy("lima");
    assert.deepEqual(studyAnnualYears("green"), ["2024"]);
    const annual = studySpatialIndicator("green", { year: "2024" });
    assert.equal(annual.detail.path, "annual/detail/green_2024.geojson");
    assert.equal(annual.rendered.kind, "geojson");
    assert.deepEqual(annual.detail.color_domain, { min: 0, max: 80 });
  } finally {
    globalThis.fetch = originalFetch;
    resetStudyRepository();
  }
});
