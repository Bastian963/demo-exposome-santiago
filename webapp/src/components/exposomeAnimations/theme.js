const BASE_THEME = {
  shell: 0x0d0e1a,
  surface: 0x101425,
  inset: 0x151b31,
  lcd: 0x09111f,
  lcdDark: 0xe6eef7,
  lcdMuted: 0x94b0c2,
  line: 0x8ca4bf,
  lineSoft: 0x27395d,
  grid: 0x1a2742,
  glow: 0xd9a441,
  pm25: 0x6e8794,
  no2: 0xb98032,
  alan: 0xd9a441,
  heat: 0xf28c38,
  social: 0x73eff7,
  noise: 0xf4b41b,
  food: 0x78d6aa,
  walk: 0xa0e426,
  wind: 0x94b0c2,
  white: 0xe6eef7,
};

export function getThemeForExposome(expo) {
  const id = expo?.id || expo?.label?.toLowerCase?.() || "pm25";
  const accent =
    id.startsWith("heat") ? BASE_THEME.heat :
    id === "wildfire" ? BASE_THEME.heat :
    (id === "noise" || id === "noise_lden") ? BASE_THEME.noise :
    id === "social_infrastructure" ? BASE_THEME.social :
    id === "healthcare" ? BASE_THEME.social :
    id === "food_environment" ? BASE_THEME.food :
    id === "food_insecurity" ? BASE_THEME.noise :
    id === "walkability" ? BASE_THEME.walk :
    id === "green" || id === "canopy" || id === "greenspace_access" ? BASE_THEME.food :
    id === "wind" ? BASE_THEME.wind :
    id === "nse" ? BASE_THEME.social :
    expo?.chamber?.mode === "safety" ? BASE_THEME.noise :
    expo?.chamber?.mode === "outcome" ? 0x94b0c2 :
    id === "alan" ? BASE_THEME.alan :
    id === "no2" ? BASE_THEME.no2 :
    BASE_THEME.pm25;
  return {
    ...BASE_THEME,
    id,
    accent,
    variant: expo?.chamber?.variant,
    particle: parsePixiColor(expo?.chamber?.particle_color, accent),
  };
}

export function applyPanelTheme(expo) {
  const panel = document.getElementById("rightPanel");
  const section = document.querySelector(".airchamber-section");
  const id = expo?.id || "pm25";
  if (panel) panel.dataset.instrumentExposome = id;
  if (section) section.dataset.instrumentExposome = id;
}

export function parsePixiColor(value, fallback = 0xffffff) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return fallback;
  const normalized = value.trim().replace(/^#/, "").replace(/^0x/i, "");
  const parsed = parseInt(normalized, 16);
  return Number.isFinite(parsed) ? parsed : fallback;
}
