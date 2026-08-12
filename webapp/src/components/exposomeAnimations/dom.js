import { applyPanelTheme } from "./theme.js";
import { mapSupportPrefix } from "../../utils/spatial-support.js";
import { formatMeasuredValue } from "../../utils/measurement-format.js";

export function getPanelElements() {
  return {
    valueLabel: document.getElementById("airchamberValueLabel"),
    value: document.getElementById("airchamberValue"),
    valueUnit: document.getElementById("airchamberValueUnit"),
    countLabel: document.getElementById("airchamberCountLabel"),
    count: document.getElementById("airchamberCount"),
    caption: document.getElementById("airchamberCaption"),
    help: document.getElementById("airchamberHelp"),
    scaleText: document.getElementById("airchamberScaleText"),
    pixelLabel: document.getElementById("pixelIndicatorLabel"),
    pixelUnit: document.getElementById("pixelIndicatorUnit"),
    sceneLabel: document.getElementById("airchamberSceneLabel"),
    sceneSublabel: document.getElementById("airchamberSceneSublabel"),
  };
}

export function updateCopy(expo) {
  const ch = expo?.chamber || {};
  const els = getPanelElements();
  if (els.valueLabel) els.valueLabel.textContent = ch.value_label || `${expo?.label || "-"}:`;
  if (els.valueUnit) els.valueUnit.textContent = ch.unit || expo?.unit || "";
  if (els.countLabel) els.countLabel.textContent = ch.count_label || "Lectura visual";
  if (els.caption) els.caption.textContent = ch.caption || "";
  if (els.help) {
    els.help.textContent = ch.help || (
      ch.mode === "safety"
        ? "Representación territorial agregada; no muestra víctimas, personas ni hechos individuales."
        : ""
    );
  }
  if (els.scaleText) els.scaleText.textContent = ch.scale_note || "";
  if (els.pixelLabel) {
    els.pixelLabel.textContent = `${mapSupportPrefix(expo?.spatial)} ${expo?.resolution || ""}`.trim();
  }
  if (els.pixelUnit) els.pixelUnit.textContent = expo?.unit || "";
  if (els.sceneLabel) els.sceneLabel.textContent = ch.scene_label || expo?.label || "Sensor";
  if (els.sceneSublabel) els.sceneSublabel.textContent = ch.scene_sublabel || "monitor exposoma";
  applyPanelTheme(expo);
}

export function updatePreviewCopy(expo, context = {}) {
  const els = getPanelElements();
  const label = context.metricLabel || expo?.label || "-";
  const unit = context.unit || expo?.unit || "";
  if (els.valueLabel) els.valueLabel.textContent = `${label}:`;
  if (els.valueUnit) els.valueUnit.textContent = unit;
  if (els.pixelUnit) els.pixelUnit.textContent = unit;
}

export function updateNumericDisplay({ value, visualCount }) {
  const els = getPanelElements();
  if (els.value) {
    els.value.textContent =
      typeof value === "number" && !Number.isNaN(value)
        ? formatMeasuredValue(value)
        : "-";
  }
  if (els.count) {
    els.count.textContent =
      typeof visualCount === "number" && Number.isFinite(visualCount)
        ? String(Math.round(visualCount))
        : "0";
  }
}

export function resetDisplay() {
  updateNumericDisplay({ value: null, visualCount: 0 });
}
