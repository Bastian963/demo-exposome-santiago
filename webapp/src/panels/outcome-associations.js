import { loadAssociations, loadOutcomesCatalog } from "../data-repository.js";
import { getPalette } from "../palette.js";
import { prefersReducedMotion } from "../utils/motion.js";

let _activeOutcomeId = null;

export async function renderOutcomeAssociations(outcomeId) {
  const panel = document.getElementById("outcomeAssociationPanel");
  if (!panel) return;
  const expo = getPalette()?.exposomes?.[outcomeId];
  const isOutcome = expo?.category === "resultados";
  panel.hidden = !isOutcome;
  document.body.classList.toggle("outcome-mode", isOutcome);
  if (!isOutcome) {
    panel.innerHTML = "";
    _activeOutcomeId = null;
    return;
  }
  _activeOutcomeId = outcomeId;
  const [catalog, associations] = await Promise.all([
    loadOutcomesCatalog().catch(() => null),
    loadAssociations().catch(() => null),
  ]);
  if (_activeOutcomeId !== outcomeId) return;
  const outcome = (catalog?.outcomes || []).find((item) => item.id === outcomeId);
  const rows = (associations?.results || []).filter(
    (item) => item.outcome_id === outcomeId && item.release_status === "released",
  );
  panel.innerHTML = `
    <div class="outcome-panel-kicker">RESULTADO · NO EXPOSOMA</div>
    <h3>${esc(outcome?.title || expo.label)}</h3>
    <p class="outcome-panel-note">Asociación ecológica territorial. No demuestra causalidad ni riesgo individual.</p>
    ${rows.length ? renderReleased(rows) : renderGate(outcome)}
  `;
  if (rows.length) wireAssociationSelector(rows);
}

function renderGate(outcome) {
  return `
    <div class="association-gate" role="status">
      <span class="association-gate-light" aria-hidden="true"></span>
      <div>
        <strong>Asociaciones en control de calidad</strong>
        <p>${esc(outcome?.association_gate || "Faltan ajustes censales y diagnóstico espacial.")}</p>
      </div>
    </div>
  `;
}

function renderReleased(rows) {
  return `
    <label class="association-select-label" for="associationExposure">Comparar con exposoma</label>
    <select id="associationExposure" class="association-select">
      ${rows.map((row, index) => `<option value="${index}">${esc(row.exposure_label || row.exposure_id)}</option>`).join("")}
    </select>
    <div id="associationResult"></div>
  `;
}

function wireAssociationSelector(rows) {
  const select = document.getElementById("associationExposure");
  const draw = () => renderAssociation(rows[Number(select?.value || 0)]);
  select?.addEventListener("change", draw);
  draw();
}

function renderAssociation(row) {
  const target = document.getElementById("associationResult");
  if (!target || !row) return;
  const points = Array.isArray(row.points) ? row.points : [];
  target.innerHTML = `
    <div class="association-readout">
      <span>Spearman <strong>${number(row.spearman_rho)}</strong></span>
      <span>RR ajustada <strong>${number(row.adjusted_rr)}</strong></span>
      <span>IC95% <strong>${number(row.ci_low)}–${number(row.ci_high)}</strong></span>
      <span>q <strong>${number(row.q_value)}</strong></span>
    </div>
    ${scatterSvg(points)}
    <p class="association-diagnostic">Moran residual: ${number(row.residual_moran_i)} · p=${number(row.residual_moran_p)}</p>
  `;
}

function scatterSvg(points) {
  if (!points.length) return '<p class="association-empty">Sin puntos públicos para este ajuste.</p>';
  const xs = points.map((point) => point.x).filter(Number.isFinite);
  const ys = points.map((point) => point.y).filter(Number.isFinite);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const sx = (x) => 16 + ((x - minX) / (maxX - minX || 1)) * 248;
  const sy = (y) => 112 - ((y - minY) / (maxY - minY || 1)) * 92;
  const reduced = prefersReducedMotion();
  return `<svg class="association-scatter ${reduced ? "reduced" : ""}" viewBox="0 0 280 128" role="img" aria-label="Dispersión territorial">
    <path d="M16 8V112H270" class="association-axis" />
    ${points.map((point, index) => `<circle cx="${sx(point.x).toFixed(1)}" cy="${sy(point.y).toFixed(1)}" r="3" style="--point-index:${index}" />`).join("")}
  </svg>`;
}

function number(value) {
  return Number.isFinite(value) ? Number(value).toFixed(2) : "—";
}

function esc(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
