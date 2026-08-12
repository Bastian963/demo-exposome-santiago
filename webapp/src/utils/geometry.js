// Point-in-polygon over GeoJSON, with no dependencies.
//
// Extracted from location-profile.js so the download tab can resolve an
// address to its administrative unit without importing the whole location
// card. Pure functions only: no DOM, no map, no fetch — which is also the only
// shape the node --test suite can cover.

export function visitCoordinates(node, visitor) {
  if (
    Array.isArray(node)
    && node.length >= 2
    && typeof node[0] === "number"
    && typeof node[1] === "number"
  ) {
    visitor(node[0], node[1]);
    return;
  }
  if (Array.isArray(node)) {
    node.forEach((child) => visitCoordinates(child, visitor));
  }
}

export function geometryBBox(geometry) {
  const points = [];
  visitCoordinates(geometry?.coordinates, (x, y) => points.push([x, y]));
  if (!points.length) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  return [minX, minY, maxX, maxY];
}

export function ringContainsPoint(ring, lon, lat) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const intersects = ((yi > lat) !== (yj > lat))
      && (lon < ((xj - xi) * (lat - yi)) / ((yj - yi) || 1e-12) + xi);
    if (intersects) inside = !inside;
  }
  return inside;
}

// A point in a hole is outside the polygon, so interior rings subtract.
export function polygonContainsPoint(rings, lon, lat) {
  if (!rings?.length || !ringContainsPoint(rings[0], lon, lat)) return false;
  for (let i = 1; i < rings.length; i++) {
    if (ringContainsPoint(rings[i], lon, lat)) return false;
  }
  return true;
}

export function geometryContainsPoint(geometry, lon, lat) {
  if (!geometry) return false;
  if (geometry.type === "Polygon") {
    return polygonContainsPoint(geometry.coordinates, lon, lat);
  }
  if (geometry.type === "MultiPolygon") {
    return geometry.coordinates.some((polygon) => polygonContainsPoint(polygon, lon, lat));
  }
  return false;
}

// Caches a bbox on the feature: a pasted batch tests many points against the
// same features, and the bbox rejects almost all of them without ray casting.
export function featureContainsPoint(feature, lon, lat) {
  if (!feature) return false;
  if (!feature._bbox) {
    feature._bbox = geometryBBox(feature.geometry);
  }
  const b = feature._bbox;
  if (!b || lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) return false;
  return geometryContainsPoint(feature.geometry, lon, lat);
}

export function findFeatureAtPoint(features, lon, lat) {
  if (!Array.isArray(features)) return null;
  return features.find((feature) => featureContainsPoint(feature, lon, lat)) || null;
}

// How many units have a *bounding box* overlapping a disc of `radiusM`, as a
// cheap fragility diagnostic. It is reported next to the value, never used to
// blend across units: the average of two comunas is a number that exists in
// neither (ADR 0004 §5).
//
// Named `unitsNearby`, not `unitsTouched`, because bbox overlap overcounts for
// an L-shaped or elongated unit. The Python side (`_administrative_value`) uses
// a real `intersects` test and reports `units_touched`; the two deliberately
// differ, and this is the loose upper bound.
export function unitsNearby(features, lon, lat, radiusM) {
  if (!Array.isArray(features) || !(radiusM > 0)) return 0;
  const degLat = radiusM / 111320;
  const degLon = degLat / Math.max(Math.cos((lat * Math.PI) / 180), 1e-6);
  const box = [lon - degLon, lat - degLat, lon + degLon, lat + degLat];
  let count = 0;
  for (const feature of features) {
    if (!feature._bbox) feature._bbox = geometryBBox(feature.geometry);
    const b = feature._bbox;
    if (!b) continue;
    if (b[0] <= box[2] && b[2] >= box[0] && b[1] <= box[3] && b[3] >= box[1]) count++;
  }
  return count;
}
