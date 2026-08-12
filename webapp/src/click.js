// Public helpers for commune profiles.
// The commune click handler lives in states/commune.js (single source
// of truth); side-panel rendering, sound, and legend updates are wired
// by main.js via window.__app.setCommune.

import { selectCommune, getMaster } from "./choropleth.js";
import { assetUrl } from "./data-repository.js";

export async function loadProfilePublic(slug) {
  try {
    const res = await fetch(assetUrl(`profiles/${slug}.json`) || `/data/profiles/${slug}.json`);
    if (res.ok) return await res.json();
  } catch {
    // fall through to the master-derived profile below
  }
  return profileFromMaster(slug);
}

// Bundles that ship no profiles/ directory (e.g. a study published before
// scripts/export_study_profiles.py ran) would otherwise 404 silently and
// never open the side panel. Build a minimal profile straight from the
// already-loaded master.geojson feature instead; only cluster/ebi/
// lisa_quadrant/timeseries are absent (they degrade to "-" in
// showSidePanelForProfile).
function profileFromMaster(slug) {
  const master = getMaster();
  const feature = master?.features?.find((f) => f.properties?.slug === slug);
  if (!feature) return null;
  const { name, slug: featureSlug, ...rest } = feature.properties;
  const indicators = {};
  for (const [key, value] of Object.entries(rest)) {
    if (typeof value === "number") indicators[key] = value;
  }
  return { name, slug: featureSlug, indicators };
}

document.getElementById("sidePanelClose")?.addEventListener("click", () => {
  const panel = document.getElementById("sidePanel");
  if (!panel) return;
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  selectCommune(null);
});
