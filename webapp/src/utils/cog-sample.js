// Read a published COG at a coordinate, at its true native pixel.
//
// Why this does NOT use `locationValues` from @geomatico/maplibre-cog-protocol,
// despite that being the library already in the bundle:
//
//   locationValues -> tilePixelFromLatLonZoom({latitude, longitude, zoom})
//
// which maps the coordinate onto the **XYZ tile pyramid**, and CogReader
// synthesises those tiles from the COG with `Math.round` on the pixel window.
// So the returned value is resampled onto the tile grid, not read from the
// raster's own grid. Measured on the published bundle at the same coordinate:
//
//   Santiago PM2.5  tile grid 24.477   native 24.477   (agreed by luck)
//   Lima     PM2.5  tile grid 23.435   native 23.038   (a different cell)
//
// That is fine for a hover tooltip, which is drawn from those same tiles, but a
// *download* must return the published value. ADR 0012 §6 makes the published
// COG the canonical source for both the tab and the CLI, so the two have to
// agree exactly. Reading the pixel directly is what makes that true.
//
// geotiff still fetches only the byte ranges it needs, so the COG benefit is
// preserved: a point read pulls one internal tile, not the whole file.

import { fromUrl } from "geotiff";

const EARTH_RADIUS_M = 6378137;

const _images = new Map();

// Forward Web Mercator. Every published detail COG is EPSG:3857.
export function toWebMercator(longitude, latitude) {
  const x = EARTH_RADIUS_M * (longitude * Math.PI) / 180;
  const clamped = Math.max(Math.min(latitude, 89.9999), -89.9999);
  const y = EARTH_RADIUS_M * Math.log(Math.tan(Math.PI / 4 + (clamped * Math.PI) / 360));
  return [x, y];
}

// Pixel indices of a projected coordinate, or null when outside the raster.
export function pixelIndex({ originX, originY, resX, resY, width, height }, x, y) {
  const col = Math.floor((x - originX) / resX);
  const row = Math.floor((originY - y) / Math.abs(resY));
  if (!(col >= 0 && col < width && row >= 0 && row < height)) return null;
  return { col, row };
}

async function imageFor(url) {
  if (!_images.has(url)) {
    _images.set(url, (async () => {
      const tiff = await fromUrl(url);
      const image = await tiff.getImage();
      const [originX, originY] = image.getOrigin();
      const [resX, resY] = image.getResolution();
      return {
        image,
        grid: {
          originX, originY, resX, resY,
          width: image.getWidth(),
          height: image.getHeight(),
        },
        noData: image.getGDALNoData(),
      };
    })());
  }
  return _images.get(url);
}

export async function cogValueAtNative(url, { longitude, latitude }, band = 1) {
  const { image, grid, noData } = await imageFor(url);
  const [x, y] = toWebMercator(longitude, latitude);
  const at = pixelIndex(grid, x, y);
  if (!at) return null;
  const rasters = await image.readRasters({
    window: [at.col, at.row, at.col + 1, at.row + 1],
    samples: [Math.max((band || 1) - 1, 0)],
  });
  const raw = Number(rasters?.[0]?.[0]);
  // Published COGs declare nodata as -Infinity, which also fails isFinite, so
  // masked cells are excluded either way.
  if (!Number.isFinite(raw)) return null;
  if (noData !== null && noData !== undefined && raw === Number(noData)) return null;
  return raw;
}

// Sample several indicators at one point, sequentially: each read is a ranged
// HTTP fetch, and a pasted batch would otherwise open hundreds at once.
export async function sampleIndicatorsAtPoint(entries, { longitude, latitude }) {
  const out = [];
  for (const entry of entries) {
    try {
      const value = await cogValueAtNative(entry.url, { longitude, latitude }, entry.band);
      out.push({ ...entry, value, status: value === null ? "no_data" : "ok" });
    } catch (error) {
      // Outside the AOI mask a read legitimately fails; that is data, not a
      // crash, and one bad address must not kill the batch.
      out.push({ ...entry, value: null, status: "read_failed", error: String(error) });
    }
  }
  return out;
}

export function clearCogCache() {
  _images.clear();
}
