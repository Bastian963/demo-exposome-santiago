// Native-study map adapter. Native products keep their provider support
// (raster, points or OSM features); the first web representation draws the AOI
// and any GeoJSON preview supplied by the publisher.
import maplibregl from "maplibre-gl";
import { assetUrl, getStudyManifest, studyAsset } from "../data-repository.js";

let _map = null;
let _onLayerClick = null;

export async function initNativeState(containerId, onLayerClick, layerId = null) {
  _onLayerClick = onLayerClick;
  const manifest = getStudyManifest();
  const bbox = manifest?.location?.bbox || [-58.55, -34.72, -58.32, -34.5];
  const center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
  if (_map) destroyNativeState();
  _map = new maplibregl.Map({
    container: containerId,
    style: makeStyle(),
    center,
    zoom: 10,
    minZoom: 7,
    maxZoom: 17,
    pixelRatio: 1,
    attributionControl: { compact: true },
  });
  _map.dragRotate.disable();
  _map.touchZoomRotate.disableRotation();
  _map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  await new Promise((resolve) => _map.once("load", resolve));
  const aoiUrl = studyAsset("aoi");
  if (aoiUrl) {
    const response = await fetch(aoiUrl);
    if (response.ok) {
      const aoi = await response.json();
      _map.addSource("native-aoi", { type: "geojson", data: aoi });
      _map.addLayer({
        id: "native-aoi-fill",
        type: "fill",
        source: "native-aoi",
        paint: { "fill-color": "#4f8fba", "fill-opacity": 0.2 },
      });
      _map.addLayer({
        id: "native-aoi-outline",
        type: "line",
        source: "native-aoi",
        paint: { "line-color": "#b8e1f2", "line-width": 2 },
      });
      fitBounds(_map, bbox);
    }
  }
  await addPreviewLayer(layerId);
  return _map;
}

async function addPreviewLayer(layerId) {
  if (!layerId || !_map) return;
  const canonicalId = layerId === "pm25" ? "air_quality_pm25" : layerId;
  const layer = getStudyManifest()?.layers?.[canonicalId];
  const assets = layer?.assets || [];
  const geojson = assets.find((asset) => String(asset.path || "").endsWith(".geojson"));
  if (!geojson) return;
  const response = await fetch(assetUrl(geojson));
  if (!response.ok) return;
  const data = await response.json();
  _map.addSource("native-preview", { type: "geojson", data });
  const geometryType = data.features?.[0]?.geometry?.type || "Point";
  if (geometryType === "Point" || geometryType === "MultiPoint") {
    _map.addLayer({
      id: "native-preview-points",
      type: "circle",
      source: "native-preview",
      paint: {
        "circle-radius": 4,
        "circle-color": "#f6c453",
        "circle-stroke-color": "#1a1c2c",
        "circle-stroke-width": 1,
      },
    });
  } else {
    _map.addLayer({
      id: "native-preview-lines",
      type: "line",
      source: "native-preview",
      paint: { "line-color": "#f6c453", "line-width": 2 },
    });
  }
}

function makeStyle() {
  return {
    version: 8,
    sources: {
      "carto-light": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#1a1c2c" } },
      { id: "basemap", type: "raster", source: "carto-light", paint: { "raster-opacity": 0.45 } },
    ],
  };
}

function fitBounds(map, bbox) {
  map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 45, duration: 0 });
}

export function getNativeMap() {
  return _map;
}

export function destroyNativeState() {
  if (_map) {
    try { _map.remove(); } catch (_) { /* map already destroyed */ }
  }
  _map = null;
  _onLayerClick = null;
}
