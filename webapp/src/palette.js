// Load palette.json and expose it as both a JS object and CSS
// custom properties. This is the single point where the palette
// gets materialized into the running app.

let palette = null;

export async function loadPalette() {
  if (palette) return palette;
  const res = await fetch("/palette.json");
  if (!res.ok) {
    throw new Error(`Failed to load palette.json: ${res.status}`);
  }
  palette = await res.json();
  applyPaletteToCSS(palette);
  return palette;
}

export function getPalette() {
  if (!palette) {
    throw new Error("Palette not loaded. Call loadPalette() first.");
  }
  return palette;
}

function applyPaletteToCSS(p) {
  const root = document.documentElement;
  // Top-level colors
  for (const [k, v] of Object.entries(p.colors)) {
    root.style.setProperty(`--${kebab(k)}`, v);
  }
  // Character
  for (const [k, v] of Object.entries(p.character)) {
    root.style.setProperty(`--char-${kebab(k)}`, v);
  }
  // Effects
  for (const [k, v] of Object.entries(p.effects)) {
    root.style.setProperty(`--eff-${kebab(k)}`, v);
  }
  // Typography sizes
  for (const [k, v] of Object.entries(p.typography)) {
    root.style.setProperty(`--${kebab(k)}`, v);
  }
  root.style.setProperty("--pixel-font", p.typography.pixel_font);
  root.style.setProperty("--body-font", p.typography.body_font);
}

function kebab(s) {
  return s.replace(/_/g, "-");
}

// Get a D3-style color scale for a given colormap name.
export function getColormap(name) {
  const p = getPalette();
  const stops = p.data_colormaps[name];
  if (!stops) {
    throw new Error(`Unknown colormap: ${name}`);
  }
  return stops;
}
