// Habbo-like navigation: the creeperLat character "walks" toward
// the commune the user clicks. This is purely visual — the map
// itself is flown to the commune via MapLibre's flyTo, and the
// creeperLat tweens to the on-screen pixel of the commune.

import { walkTo } from "./sprite.js";
import { play } from "../sound.js";

let _lastTarget = null;

export async function navigateTo(map, lon, lat, opts = {}) {
  const duration = opts.duration ?? 1100;
  const zoom = opts.zoom ?? Math.max(map.getZoom(), 10);

  map.flyTo({
    center: [lon, lat],
    zoom,
    duration,
    essential: true,
  });

  // Compute target pixel for creeperLat.
  const pixel = map.project([lon, lat]);
  const mapRect = document.getElementById("map").getBoundingClientRect();
  const containerEl = document.getElementById("characterContainer");
  const containerRect = containerEl.getBoundingClientRect();
  const targetX = pixel.x - (mapRect.left - containerRect.left) - containerRect.width / 2;
  const targetY = pixel.y - (mapRect.top - containerRect.top) - containerRect.height;

  await walkTo(targetX, targetY, duration);
  play("footstep");
  _lastTarget = { lon, lat };
}

export function getLastTarget() {
  return _lastTarget;
}
