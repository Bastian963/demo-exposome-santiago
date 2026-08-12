const SPATIAL_UNIT_LABELS = {
  commune: ["comuna", "comunas"],
  admin_unit: ["unidad administrativa", "unidades administrativas"],
  distrito: ["distrito", "distritos"],
  comuna_corregimiento: ["comuna o corregimiento", "comunas y corregimientos"],
  alcaldia: ["alcaldía", "alcaldías"],
  municipio: ["municipio", "municipios"],
  partido: ["partido", "partidos"],
  postal_code: ["código postal", "códigos postales"],
  native_product: ["producto nativo", "productos nativos"],
};

export function spatialUnitLabel(unitType, { plural = false } = {}) {
  const labels = SPATIAL_UNIT_LABELS[unitType]
    || ["unidad administrativa", "unidades administrativas"];
  return labels[plural ? 1 : 0];
}
