// Continent/city selector panels for the LATAM globe screen.
// Left panel lists continents; right panel lists the cities of the
// selected continent. Only cities with available exposome data are clickable.

import { play } from "../sound.js";
import { spatialUnitLabel } from "../utils/spatial-unit.js";

let _left = null;
let _right = null;
let _cities = [];
let _continents = {};
let _activeContinent = null;
let _onCitySelect = null;

export function initLatamCityPanels(container, data, onCitySelect) {
  destroyLatamCityPanels();
  _cities = data.cities || [];
  _continents = data.continents || {};
  _onCitySelect = onCitySelect;

  const slugs = Object.keys(_continents);
  if (!slugs.length) return;
  const withCities = new Set(_cities.map((c) => c.continent));
  _activeContinent = slugs.find((s) => withCities.has(s)) || slugs[0];

  _left = document.createElement("aside");
  _left.className = "latam-panel latam-panel--left";
  _left.innerHTML = `
    <h2 class="latam-panel-title">CONTINENTES</h2>
    <div class="latam-panel-body"></div>
  `;
  const leftBody = _left.querySelector(".latam-panel-body");
  for (const slug of slugs) {
    const cities = _cities.filter((c) => c.continent === slug);
    const available = cities.filter((c) => c.available).length;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "latam-continent-btn";
    if (!cities.length) btn.classList.add("is-empty");
    btn.dataset.continent = slug;
    btn.innerHTML = `
      <span class="latam-continent-name">${escHtml(_continents[slug].label)}</span>
      <span class="latam-continent-meta">${
        cities.length
          ? `${available}/${cities.length} ${cities.length === 1 ? "ciudad" : "ciudades"}`
          : "próximamente"
      }</span>
    `;
    btn.addEventListener("click", () => {
      play("click");
      _activeContinent = slug;
      renderContinentButtons();
      renderCityList();
    });
    leftBody.appendChild(btn);
  }

  _right = document.createElement("aside");
  _right.className = "latam-panel latam-panel--right";
  _right.innerHTML = `
    <h2 class="latam-panel-title">CIUDADES</h2>
    <div class="latam-panel-body"></div>
  `;

  container.appendChild(_left);
  container.appendChild(_right);
  renderContinentButtons();
  renderCityList();
}

export function destroyLatamCityPanels() {
  _left?.remove();
  _right?.remove();
  _left = null;
  _right = null;
  _cities = [];
  _continents = {};
  _activeContinent = null;
  _onCitySelect = null;
}

function renderContinentButtons() {
  if (!_left) return;
  _left.querySelectorAll(".latam-continent-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.continent === _activeContinent);
  });
}

function renderCityList() {
  if (!_right) return;
  const body = _right.querySelector(".latam-panel-body");
  body.innerHTML = "";
  const cities = _cities.filter((c) => c.continent === _activeContinent);
  if (!cities.length) {
    const empty = document.createElement("p");
    empty.className = "latam-panel-empty";
    empty.textContent = "Sin ciudades aún. Próximamente.";
    body.appendChild(empty);
    return;
  }
  for (const city of cities) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `latam-city-btn ${city.available ? "" : "is-coming-soon"}`.trim();
    btn.disabled = !city.available;
    btn.innerHTML = `
      ${city.marker_icon
        ? `<img class="latam-city-icon" src="${escHtml(city.marker_icon)}" alt="" />`
        : '<span class="latam-city-icon latam-city-icon--placeholder" aria-hidden="true"></span>'}
      <span class="latam-city-text">
        <span class="latam-city-name">${escHtml(city.name)}</span>
        <span class="latam-city-meta">${
          city.available
            ? city.mode === "native"
              ? `modo nativo · ${city.n_layers} capas`
              : `${city.n_communes} ${spatialUnitLabel(city.unit_type, { plural: true })} · ${city.n_layers} capas`
            : "PROXIMAMENTE"
        }${city.available && city.publication_tier === "preview"
          ? ' <span class="latam-city-tier">VISTA PREVIA</span>'
          : ""}</span>
      </span>
    `;
    if (city.available) {
      btn.addEventListener("click", () => {
        play("click");
        if (_onCitySelect) _onCitySelect(city.slug);
      });
    }
    body.appendChild(btn);
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
