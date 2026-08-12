// Commune state: the actual city zoomed in with 52 communes
// rendered as a choropleth. Click on a commune loads its profile
// and animates the creeperLat.

import maplibregl from "maplibre-gl";
import { loadMaster, addChoropleth, selectCommune, getMaster } from "../choropleth.js";
import { initAirchamber, destroyAirchamber } from "../visualizations/airchamber.js";
import { getStudyManifest } from "../data-repository.js";

let _map = null;
let _onCommuneClick = null;
let _mapCenter = [-70.65, -33.45];

export async function initCommuneState(mapContainerId, onCommuneClick, exposomeId = "pm25", options = {}) {
  _onCommuneClick = onCommuneClick;
  const manifest = getStudyManifest();
  const bbox = manifest?.location?.bbox;
  _mapCenter = options.center || (Array.isArray(bbox) && bbox.length === 4
    ? [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    : [-70.65, -33.45]);
  if (!_map) {
    _map = new maplibregl.Map({
      container: mapContainerId,
      style: makeCommuneStyle(),
      center: _mapCenter,
      zoom: options.zoom || 9,
      minZoom: options.minZoom || 5,
      maxZoom: options.maxZoom || 16,
      pixelRatio: 1,
      attributionControl: { compact: true },
    });
    _map.dragRotate.disable();
    _map.touchZoomRotate.disableRotation();
    _map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
  }

  await new Promise((resolve) => {
    if (_map.loaded()) resolve();
    else _map.once("load", resolve);
  });

  // Load the master GeoJSON and add the selected exposome's choropleth.
  await loadMaster(_map);
  await addChoropleth(exposomeId);

  // Fit the map to the Santiago region so all 52 communes are visible.
  fitToStudy(_map);

  // Initialize the air chamber in the right panel. Fire-and-forget
  // so a 0x0 container doesn't block the rest of the transition.
  initAirchamber("airchamberCanvas").catch((e) => {
    console.warn("initAirchamber failed:", e);
  });

  // Click handler for communes.
  _map.on("click", "communes-fill", (e) => {
    if (!e.features || !e.features[0]) return;
    const f = e.features[0];
    const props = f.properties;
    const slug = props.slug;
    if (!slug) return;
    selectCommune(slug);
    const centroid = getCentroid(f.geometry);
    if (_onCommuneClick) {
      _onCommuneClick({
        slug,
        name: props.name,
        centroid,
      });
    }
  });
}

function makeCommuneStyle() {
  return {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      "carto-light": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
          "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
          "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> ' +
          '&copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#1a1c2c" },
      },
      {
        id: "basemap",
        type: "raster",
        source: "carto-light",
        paint: {
          "raster-opacity": 0.45,
          "raster-saturation": -0.6,
          "raster-contrast": 0.05,
        },
      },
    ],
  };
}

function getCentroid(geometry) {
  if (geometry.type === "Polygon") {
    return ringAverage(geometry.coordinates[0]);
  } else if (geometry.type === "MultiPolygon") {
    return ringAverage(geometry.coordinates[0][0]);
  }
  return _mapCenter;
}

function ringAverage(ring) {
  let sx = 0, sy = 0;
  for (const [x, y] of ring) {
    sx += x;
    sy += y;
  }
  return [sx / ring.length, sy / ring.length];
}

export function getCommuneMap() {
  return _map;
}

export function flyToCommune(centroid, zoom = 10, duration = 1100) {
  if (!_map) return Promise.resolve();
  return new Promise((resolve) => {
    _map.flyTo({
      center: centroid,
      zoom,
      duration,
      essential: true,
      complete: resolve,
    });
  });
}

export function destroyCommuneState() {
  if (!_map) return;
  try {
    _map.remove();
  } catch (e) {
    /* ignore if already removed */
  }
  _map = null;
  _onCommuneClick = null;
  destroyAirchamber();
}

// Fit the map to the bounding box of the selected study's spatial units
// with enough padding to show the full region + context. The user
// can zoom in further from here.
function fitToStudy(map) {
  try {
    const master = getMaster();
    if (!master || !master.features || !master.features.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const f of master.features) {
      const g = f.geometry;
      if (!g) continue;
      const coords = g.type === "Polygon" ? g.coordinates : g.coordinates[0];
      for (const ring of g.type === "Polygon" ? [coords] : coords) {
        for (const [x, y] of ring) {
          if (x < minX) minX = x;
          if (y < minY) minY = y;
          if (x > maxX) maxX = x;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (!isFinite(minX)) return;
    map.fitBounds(
      [[minX, minY], [maxX, maxY]],
      { padding: 80, duration: 0, maxZoom: 9.5 },
    );
  } catch (e) {
    console.warn("fitToStudy failed:", e);
  }
}
