// LATAM state: pixel-art earth globe with animated starfield and city selector.
// The commune view still uses MapLibre; this state owns only the start screen.

import { play } from "../sound.js";
import { initLatamCityPanels, destroyLatamCityPanels } from "../panels/latam-cities.js";
import { loadCatalog } from "../data-repository.js";
import { prefersReducedMotion } from "../utils/motion.js";
import { spatialUnitLabel } from "../utils/spatial-unit.js";

const DEFAULT_LON = -58;
const DEFAULT_LAT = -22;
const DEFAULT_ZOOM = 0.82;
const MIN_ZOOM = 0.55;
const MAX_ZOOM = 2.1;
const EARTH_TILE_ZOOM = 2;
const GLOBE_SPIN_DEGREES_PER_SECOND = 8;
const GLOBE_SPIN_RESUME_MS = 5000;
const PIXEL_SIZE = 4; // CSS px per canvas texel; the CSS upscale keeps edges crisp
const EARTH_TEXTURE_WIDTH = 128;
const FOCUS_TWEEN_MS = 1700;
const FOCUS_ZOOM = 1.9;
const METEOR_LIFE_MS = 700;

// Earth ramp: palette.json blues for water, muted greens for land.
const COLOR_DEEP_OCEAN = [0x29, 0x36, 0x6f];
const COLOR_OCEAN = [0x3b, 0x5d, 0xc9];
const COLOR_SHALLOW = [0x41, 0xa6, 0xf6];
const COLOR_LAND_DARK = [0x3d, 0x5c, 0x32];
const COLOR_LAND = [0x5a, 0x8a, 0x4a];
const COLOR_LAND_LIGHT = [0x7f, 0xad, 0x6e];
const COLOR_DESERT = [0xf4, 0xb4, 0x1b];
const COLOR_ICE = [0xf4, 0xf4, 0xf4];

let _container = null;
let _canvas = null;
let _ctx = null;
let _onCityClick = null;
let _onOpenAnalytics = null;
let _onOpenDownload = null;
let _cities = null;
let _markers = [];
let _texture = null;
let _frame = null;
let _lastTs = null;
let _spinPaused = false;
let _resumeTimer = null;
let _dragging = false;
let _dragStart = null;
let _centerLon = DEFAULT_LON;
let _centerLat = DEFAULT_LAT;
let _zoom = DEFAULT_ZOOM;
let _cssScale = PIXEL_SIZE;
let _stars = [];
let _meteor = null;
let _tween = null;

export async function initLatamState(containerId, mapContainerId, onCityClick, onOpenAnalytics, onOpenDownload) {
  destroyLatamState();
  _onCityClick = onCityClick;
  _onOpenAnalytics = onOpenAnalytics;
  _onOpenDownload = onOpenDownload;
  const data = await loadCatalog();
  _cities = data.cities || [];
  _centerLon = data.global_center?.[0] ?? DEFAULT_LON;
  _centerLat = data.global_center?.[1] ?? DEFAULT_LAT;
  _zoom = data.global_zoom ?? DEFAULT_ZOOM;

  _container = document.getElementById(mapContainerId);
  if (!_container) throw new Error(`#${mapContainerId} not found`);
  _container.innerHTML = "";
  _container.classList.add("globe-map");

  _canvas = document.createElement("canvas");
  _canvas.className = "globe-canvas";
  _container.appendChild(_canvas);
  _ctx = _canvas.getContext("2d", { willReadFrequently: true });

  const title = document.createElement("div");
  title.className = "globe-title";
  title.textContent = "GEMMA";
  _container.appendChild(title);

  const tagline = document.createElement("div");
  tagline.className = "globe-tagline";
  tagline.textContent = "GLOBAL EXPOSOME MODELING, MAPPING & ANALYTICS";
  _container.appendChild(tagline);

  if (_onOpenAnalytics) {
    const analyticsButton = document.createElement("button");
    analyticsButton.type = "button";
    analyticsButton.className = "globe-analytics-button";
    analyticsButton.textContent = "ANALYTICS";
    analyticsButton.addEventListener("click", () => {
      play("click");
      _onOpenAnalytics();
    });
    _container.appendChild(analyticsButton);
  }

  if (_onOpenDownload) {
    const downloadButton = document.createElement("button");
    downloadButton.type = "button";
    downloadButton.className = "globe-analytics-button globe-download-button";
    downloadButton.textContent = "DESCARGA POR PUNTO";
    downloadButton.addEventListener("click", () => {
      play("click");
      _onOpenDownload();
    });
    _container.appendChild(downloadButton);
  }

  const prompt = document.createElement("div");
  prompt.className = "globe-prompt";
  prompt.textContent = "CLICK THE PLANET TO EXPLORE";
  _container.appendChild(prompt);

  const attribution = document.createElement("div");
  attribution.className = "globe-attribution";
  attribution.textContent = "Earth imagery: Esri, Maxar, Earthstar Geographics";
  _container.appendChild(attribution);

  _texture = await loadEarthTexture();
  createMarkers();
  initLatamCityPanels(_container, data, selectCity);
  wireInteraction();
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  startLoop();
}

export function getLatamMap() {
  return null;
}

export function flyToCity(slug) {
  const city = _cities?.find((c) => c.slug === slug);
  if (!city) return Promise.resolve();
  _centerLon = city.center[0];
  _centerLat = clamp(city.center[1], -62, 62);
  _zoom = Math.min(MAX_ZOOM, 1.35);
  pauseSpin();
  return Promise.resolve();
}

export function focusCity(slug) {
  const city = _cities?.find((c) => c.slug === slug);
  if (!city) return Promise.resolve({ cancelled: true });
  cancelTween();
  pauseSpin();
  play("whoosh");
  return new Promise((resolve) => {
    _tween = {
      start: null,
      dur: FOCUS_TWEEN_MS,
      fromLon: _centerLon,
      fromLat: _centerLat,
      fromZoom: _zoom,
      dLon: wrapLng(city.center[0] - _centerLon),
      toLat: clamp(city.center[1], -62, 62),
      toZoom: Math.min(MAX_ZOOM, FOCUS_ZOOM),
      resolve,
    };
  });
}

export function resetLatamView() {
  cancelTween();
  _centerLon = DEFAULT_LON;
  _centerLat = DEFAULT_LAT;
  _zoom = DEFAULT_ZOOM;
  scheduleSpinResume();
  return Promise.resolve();
}

export function destroyLatamState() {
  stopLoop();
  window.removeEventListener("resize", resizeCanvas);
  if (_resumeTimer) clearTimeout(_resumeTimer);
  _resumeTimer = null;
  cancelTween();
  destroyLatamCityPanels();
  _markers.forEach((m) => m.el.remove());
  _markers = [];
  if (_container) {
    _container.classList.remove("globe-map");
    _container.innerHTML = "";
  }
  _container = null;
  _canvas = null;
  _ctx = null;
  _texture = null;
  _cities = null;
  _onCityClick = null;
  _onOpenAnalytics = null;
  _onOpenDownload = null;
  _dragging = false;
  _stars = [];
  _meteor = null;
  _cssScale = PIXEL_SIZE;
  _spinPaused = false;
}

function selectCity(slug) {
  // The focus tween is decorative. Navigation must not depend on the
  // requestAnimationFrame loop completing: Safari can throttle that loop and
  // otherwise leave a city click looking inert indefinitely.
  void focusCity(slug);
  if (_onCityClick) _onCityClick(slug);
}

function cancelTween() {
  if (!_tween) return;
  const tween = _tween;
  _tween = null;
  tween.resolve({ cancelled: true });
}

async function loadEarthTexture() {
  const tileCount = 2 ** EARTH_TILE_ZOOM;
  const size = tileCount * 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#073047";
  ctx.fillRect(0, 0, size, size);

  const tiles = [];
  for (let y = 0; y < tileCount; y++) {
    for (let x = 0; x < tileCount; x++) {
      const url = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${EARTH_TILE_ZOOM}/${y}/${x}`;
      tiles.push(loadImage(url).then((img) => ctx.drawImage(img, x * 256, y * 256, 256, 256)).catch(() => {}));
    }
  }
  await Promise.all(tiles);

  try {
    return quantizeTexture(canvas);
  } catch (_) {
    return makeFallbackTexture();
  }
}

// Downscale to a tiny texture and snap every pixel to the earth ramp.
// Halving steps give an area-average downscale (a single drawImage may
// skip pixels on large ratios in some browsers).
function quantizeTexture(source) {
  let current = source;
  while (current.width / 2 >= EARTH_TEXTURE_WIDTH) {
    const half = document.createElement("canvas");
    half.width = Math.round(current.width / 2);
    half.height = Math.round(current.height / 2);
    const hctx = half.getContext("2d");
    hctx.imageSmoothingEnabled = true;
    hctx.drawImage(current, 0, 0, half.width, half.height);
    current = half;
  }
  const width = EARTH_TEXTURE_WIDTH;
  const height = Math.round(width * (current.height / current.width));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(current, 0, 0, width, height);
  const image = ctx.getImageData(0, 0, width, height);
  const px = image.data;
  for (let i = 0; i < px.length; i += 4) {
    const color = classifyEarthColor(px[i], px[i + 1], px[i + 2]);
    px[i] = color[0];
    px[i + 1] = color[1];
    px[i + 2] = color[2];
  }
  return { width, height, data: px };
}

function classifyEarthColor(r, g, b) {
  const lum = (r + g + b) / 3;
  if (lum > 190) return COLOR_ICE;
  if (b > r && b >= g) {
    if (lum < 35) return COLOR_DEEP_OCEAN;
    if (lum < 80) return COLOR_OCEAN;
    return COLOR_SHALLOW;
  }
  if (r > 115 && r > b + 40 && g > b + 15) return COLOR_DESERT;
  if (lum < 70) return COLOR_LAND_DARK;
  if (lum < 115) return COLOR_LAND;
  return COLOR_LAND_LIGHT;
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

function makeFallbackTexture() {
  const width = 1024;
  const height = 512;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#073047";
  ctx.fillRect(0, 0, width, height);
  drawFallbackLand(ctx, width, height);
  return quantizeTexture(canvas);
}

function drawFallbackLand(ctx, w, h) {
  ctx.fillStyle = "#4f6f3f";
  [
    [0.28, 0.47, 0.1, 0.2], [0.31, 0.67, 0.065, 0.16],
    [0.49, 0.36, 0.09, 0.08], [0.54, 0.52, 0.1, 0.18],
    [0.69, 0.38, 0.16, 0.12], [0.78, 0.55, 0.08, 0.13],
  ].forEach(([x, y, rx, ry]) => {
    ctx.beginPath();
    ctx.ellipse(x * w, y * h, rx * w, ry * h, 0, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.fillStyle = "#9c875f";
  ctx.fillRect(w * 0.47, h * 0.38, w * 0.12, h * 0.07);
  ctx.fillRect(w * 0.62, h * 0.33, w * 0.08, h * 0.06);
}

function createMarkers() {
  _markers = _cities.map((city) => {
    const el = document.createElement("div");
    el.className = `city-marker ${city.available ? "is-available" : "is-disabled"}`;
    el.innerHTML = `
      <span class="city-marker-core">
        ${city.marker_icon
          ? `<img src="${escHtml(city.marker_icon)}" alt="${escHtml(city.name)}" />`
          : '<span class="city-marker-placeholder" aria-hidden="true"></span>'}
      </span>
      <span class="city-marker-label">${escHtml(city.name)}</span>
    `;
    const tierNote = city.publication_tier === "preview" ? " - vista previa: faltan detalles espaciales" : "";
    el.title = city.available
      ? `${city.name} - ${city.n_communes} ${spatialUnitLabel(city.unit_type, { plural: true })} - ${city.n_layers} capas${tierNote}`
      : `${city.name} - próximamente`;
    if (city.available) {
      el.addEventListener("click", () => selectCity(city.slug));
    }
    _container.appendChild(el);
    return { city, el };
  });
}

function wireInteraction() {
  _canvas.addEventListener("pointerdown", (e) => {
    cancelTween();
    _dragging = true;
    _canvas.classList.add("is-dragging");
    _canvas.setPointerCapture(e.pointerId);
    _dragStart = { x: e.clientX, y: e.clientY, lon: _centerLon, lat: _centerLat };
    pauseSpin();
  });
  _canvas.addEventListener("pointermove", (e) => {
    if (!_dragging || !_dragStart) return;
    const dx = e.clientX - _dragStart.x;
    const dy = e.clientY - _dragStart.y;
    _centerLon = wrapLng(_dragStart.lon - dx / (4.2 * _zoom));
    _centerLat = clamp(_dragStart.lat + dy / (4.8 * _zoom), -64, 64);
  });
  _canvas.addEventListener("pointerup", endDrag);
  _canvas.addEventListener("pointercancel", endDrag);
  _canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    cancelTween();
    pauseSpin();
    const next = _zoom * (e.deltaY > 0 ? 0.92 : 1.09);
    _zoom = clamp(next, MIN_ZOOM, MAX_ZOOM);
    scheduleSpinResume();
  }, { passive: false });
}

function endDrag(e) {
  if (!_dragging) return;
  _dragging = false;
  _dragStart = null;
  _canvas.classList.remove("is-dragging");
  try { _canvas.releasePointerCapture(e.pointerId); } catch (_) {}
  scheduleSpinResume();
}

function resizeCanvas() {
  if (!_canvas || !_container) return;
  const rect = _container.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width / PIXEL_SIZE));
  const h = Math.max(1, Math.round(rect.height / PIXEL_SIZE));
  _canvas.width = w;
  _canvas.height = h;
  _canvas.style.width = `${rect.width}px`;
  _canvas.style.height = `${rect.height}px`;
  _cssScale = rect.width / w;
  makeStars(w, h);
}

function makeStars(w, h) {
  const count = Math.round((w * h) / 220);
  _stars = Array.from({ length: count }, () => ({
    x: Math.floor(Math.random() * w),
    y: Math.floor(Math.random() * h),
    size: Math.random() < 0.12 ? 2 : 1,
    phase: Math.random() * Math.PI * 2,
    speed: 0.5 + Math.random() * 1.5,
    color: pickStarColor(),
  }));
}

function pickStarColor() {
  const r = Math.random();
  if (r < 0.72) return "#f4f4f4";
  if (r < 0.86) return "#94b0c2";
  if (r < 0.95) return "#73eff7";
  return "#f4b41b";
}

function startLoop() {
  stopLoop();
  const step = (ts) => {
    const dt = _lastTs == null ? 0 : Math.min(64, ts - _lastTs) / 1000;
    // Reduced motion: navigation tweens land instantly, the decorative
    // auto-spin and meteors stop; the loop itself stays alive because it
    // also drives drag interaction.
    const reduced = prefersReducedMotion();
    if (_tween) {
      if (_tween.start == null) _tween.start = ts;
      const p = reduced ? 1 : easeInOutCubic(Math.min(1, (ts - _tween.start) / _tween.dur));
      _centerLon = wrapLng(_tween.fromLon + _tween.dLon * p);
      _centerLat = _tween.fromLat + (_tween.toLat - _tween.fromLat) * p;
      _zoom = _tween.fromZoom + (_tween.toZoom - _tween.fromZoom) * p;
      if (p >= 1) {
        const tween = _tween;
        _tween = null;
        tween.resolve({ cancelled: false });
      }
    } else if (dt > 0 && !_spinPaused && !_dragging && !reduced) {
      _centerLon = wrapLng(_centerLon + GLOBE_SPIN_DEGREES_PER_SECOND * dt);
    }
    if (!_meteor && dt > 0 && !reduced && Math.random() < dt / 9) spawnMeteor(ts);
    _lastTs = ts;
    render(ts);
    _frame = requestAnimationFrame(step);
  };
  _frame = requestAnimationFrame(step);
}

function stopLoop() {
  if (_frame) cancelAnimationFrame(_frame);
  _frame = null;
  _lastTs = null;
}

function pauseSpin() {
  _spinPaused = true;
  if (_resumeTimer) clearTimeout(_resumeTimer);
  _resumeTimer = null;
}

function scheduleSpinResume() {
  if (_resumeTimer) clearTimeout(_resumeTimer);
  _resumeTimer = setTimeout(() => {
    _spinPaused = false;
    _lastTs = null;
    _resumeTimer = null;
  }, GLOBE_SPIN_RESUME_MS);
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function render(ts) {
  if (!_ctx || !_canvas || !_texture) return;
  const width = _canvas.width;
  const height = _canvas.height;
  const cx = width * 0.5;
  const cy = height * 0.5;
  const radius = Math.min(width, height) * 0.42 * _zoom;
  _ctx.clearRect(0, 0, width, height);
  _ctx.imageSmoothingEnabled = false;

  const minX = Math.max(0, Math.floor(cx - radius));
  const maxX = Math.min(width - 1, Math.ceil(cx + radius));
  const minY = Math.max(0, Math.floor(cy - radius));
  const maxY = Math.min(height - 1, Math.ceil(cy + radius));
  const image = _ctx.createImageData(maxX - minX + 1, maxY - minY + 1);
  const lon0 = toRad(_centerLon);
  const lat0 = toRad(_centerLat);
  const sinLat0 = Math.sin(lat0);
  const cosLat0 = Math.cos(lat0);

  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const nx = (x - cx) / radius;
      const ny = -(y - cy) / radius;
      const rr = nx * nx + ny * ny;
      const i = ((y - minY) * image.width + (x - minX)) * 4;
      if (rr > 1) {
        image.data[i + 3] = 0;
        continue;
      }
      const rho = Math.sqrt(rr);
      const cosc = Math.sqrt(1 - rr);
      const lat = rho === 0
        ? lat0
        : Math.asin(cosc * sinLat0 + (ny * Math.sin(Math.asin(rho)) * cosLat0) / rho);
      const lon = lon0 + Math.atan2(
        nx * Math.sin(Math.asin(rho)),
        rho * cosLat0 * cosc - ny * sinLat0 * Math.sin(Math.asin(rho)),
      );
      const src = sampleEarth(lon, lat);
      // Discrete limb-shading bands with a checker dither at the seams.
      const banded = cosc + (((x ^ y) & 1) ? 0.035 : -0.035);
      const shade = banded > 0.72 ? 1 : banded > 0.42 ? 0.84 : 0.62;
      image.data[i] = src[0] * shade;
      image.data[i + 1] = src[1] * shade;
      image.data[i + 2] = src[2] * shade;
      image.data[i + 3] = 255;
    }
  }
  _ctx.putImageData(image, minX, minY);
  drawStars(ts, cx, cy, radius);
  drawGlobeFrame(cx, cy, radius);
  updateMarkers(cx, cy, radius, lon0, lat0, sinLat0, cosLat0);
}

// Stars go after putImageData (which replaces pixels, including the
// transparent corners of the globe's bounding box) and skip the disk.
function drawStars(ts, cx, cy, radius) {
  // Reduced motion: freeze the twinkle at a fixed phase.
  const t = prefersReducedMotion() ? 0 : ts / 1000;
  const rim = (radius + 2) * (radius + 2);
  for (const star of _stars) {
    const dx = star.x - cx;
    const dy = star.y - cy;
    if (dx * dx + dy * dy < rim) continue;
    const tw = 0.5 + 0.5 * Math.sin(t * star.speed + star.phase);
    _ctx.globalAlpha = 0.25 + 0.75 * tw * tw;
    _ctx.fillStyle = star.color;
    _ctx.fillRect(star.x, star.y, star.size, star.size);
  }
  _ctx.globalAlpha = 1;
  drawMeteor(ts, cx, cy, radius);
}

function spawnMeteor(ts) {
  if (!_canvas) return;
  const w = _canvas.width;
  _meteor = {
    born: ts,
    x: Math.random() * w * 0.7,
    y: Math.random() * _canvas.height * 0.25,
    vx: (0.35 + Math.random() * 0.2) * w,
    vy: (0.16 + Math.random() * 0.1) * w,
  };
}

function drawMeteor(ts, cx, cy, radius) {
  if (!_meteor) return;
  const age = ts - _meteor.born;
  if (age > METEOR_LIFE_MS) {
    _meteor = null;
    return;
  }
  const t = age / 1000;
  const fade = 1 - age / METEOR_LIFE_MS;
  const rim = (radius + 2) * (radius + 2);
  _ctx.fillStyle = "#f4f4f4";
  for (let i = 0; i < 4; i++) {
    const trail = t - i * 0.03;
    if (trail < 0) break;
    const x = Math.round(_meteor.x + _meteor.vx * trail);
    const y = Math.round(_meteor.y + _meteor.vy * trail);
    const dx = x - cx;
    const dy = y - cy;
    if (dx * dx + dy * dy < rim) continue;
    _ctx.globalAlpha = fade * (1 - i * 0.22);
    _ctx.fillRect(x, y, 1, 1);
  }
  _ctx.globalAlpha = 1;
}

function sampleEarth(lon, lat) {
  const clampedLat = clamp(lat, toRad(-85), toRad(85));
  const u = ((lon + Math.PI) / (Math.PI * 2) % 1 + 1) % 1;
  const mercY = (1 - Math.log(Math.tan(clampedLat) + 1 / Math.cos(clampedLat)) / Math.PI) / 2;
  const tx = Math.floor(u * (_texture.width - 1));
  const ty = Math.floor(clamp(mercY, 0, 1) * (_texture.height - 1));
  const idx = (ty * _texture.width + tx) * 4;
  return [_texture.data[idx], _texture.data[idx + 1], _texture.data[idx + 2]];
}

function drawGlobeFrame(cx, cy, radius) {
  _ctx.strokeStyle = "rgba(148, 176, 194, 0.45)";
  _ctx.lineWidth = 1;
  _ctx.beginPath();
  _ctx.arc(cx, cy, radius + 0.5, 0, Math.PI * 2);
  _ctx.stroke();
}

function updateMarkers(cx, cy, radius, lon0, lat0, sinLat0, cosLat0) {
  for (const marker of _markers) {
    const [lng, latDeg] = marker.city.center || [0, 0];
    const lon = toRad(lng);
    const lat = toRad(latDeg);
    const dlon = lon - lon0;
    const sinLat = Math.sin(lat);
    const cosLat = Math.cos(lat);
    const visible = sinLat0 * sinLat + cosLat0 * cosLat * Math.cos(dlon);
    if (visible <= -0.02) {
      marker.el.hidden = true;
      continue;
    }
    const x = radius * cosLat * Math.sin(dlon);
    const y = -radius * (cosLat0 * sinLat - sinLat0 * cosLat * Math.cos(dlon));
    marker.el.hidden = false;
    marker.el.style.transform = `translate(${(cx + x) * _cssScale}px, ${(cy + y) * _cssScale}px) translate(-50%, -50%)`;
  }
}

function escHtml(s) {
  if (typeof s !== "string") return s == null ? "" : String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toRad(v) {
  return v * Math.PI / 180;
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

function wrapLng(lng) {
  return ((lng + 180) % 360 + 360) % 360 - 180;
}
