// Classify a pasted line as coordinates, a postal code or an address.
//
// Mirrors src/exposome/geocoding.py::classify_input. The two implementations
// must agree, because the same paste has to behave the same whether it goes
// through the tab or through `exposome extract-points`.

export const KIND_LATLON = "latlon";
export const KIND_ADDRESS = "address";
export const KIND_POSTAL = "postal";
export const KIND_EMPTY = "empty";

export const PRECISION_EXACT = "latlon_exact";

// Only used to classify a line whose country the user already declared.
// Nothing here implies the code can be resolved to a geography.
export const POSTAL_PATTERNS = {
  CL: /^\d{7}$/,
  MX: /^\d{5}$/,
  ES: /^\d{5}$/,
  PE: /^\d{5}$/,
  CO: /^\d{6}$/,
  BR: /^\d{5}-?\d{3}$/,
  // Argentina's CPA is a letter, four digits and three letters; the legacy
  // four-digit form is still written by hand.
  AR: /^([A-Za-z]\d{4}[A-Za-z]{3}|\d{4})$/,
};

const LATLON = /^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;
const COUNTRY_PREFIX = /^\s*([A-Za-z]{2})[\s:]+(.+)$/;

export function parseLatLon(text) {
  const match = LATLON.exec(String(text ?? ""));
  if (!match) return null;
  const first = Number(match[1]);
  const second = Number(match[2]);
  // "lat, lon" is what people paste from map apps.
  let lat = first;
  let lon = second;
  if (Math.abs(lat) > 90 && Math.abs(lon) <= 90) {
    lat = second;
    lon = first;
  }
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lon, lat };
}

export function normalizePostal(countryCode, value) {
  const country = String(countryCode || "").toUpperCase();
  const pattern = POSTAL_PATTERNS[country];
  if (!pattern) return null;
  const candidate = String(value ?? "").replace(/\s/g, "");
  return pattern.test(candidate) ? candidate.toUpperCase() : null;
}

// A bare five-digit number is ambiguous between MX, ES and PE, so the country
// for postal lines is declared — by an inline prefix or by postalCountry —
// never inferred.
export function classifyInput(line, postalCountry = null) {
  const raw = String(line ?? "").trim();
  if (!raw) return { raw, kind: KIND_EMPTY };

  const coords = parseLatLon(raw);
  if (coords) return { raw, kind: KIND_LATLON, ...coords };
  if (LATLON.test(raw)) {
    // Shaped like coordinates but out of range: treat as text, and say so.
    return { raw, kind: KIND_ADDRESS, note: "looks like coordinates but is out of range" };
  }

  let candidate = raw;
  let country = String(postalCountry || "").toUpperCase() || null;
  const prefixed = COUNTRY_PREFIX.exec(raw);
  if (prefixed && POSTAL_PATTERNS[prefixed[1].toUpperCase()]) {
    country = prefixed[1].toUpperCase();
    candidate = prefixed[2].trim();
  }

  if (country) {
    const postalCode = normalizePostal(country, candidate);
    if (postalCode) return { raw, kind: KIND_POSTAL, postalCode, country };
  }
  return { raw, kind: KIND_ADDRESS, country };
}

export function classifyLines(text, postalCountry = null) {
  return String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line, index) => ({
      queryId: `point_${String(index + 1).padStart(4, "0")}`,
      ...classifyInput(line, postalCountry),
    }));
}

export function summarizeKinds(classified) {
  const counts = { [KIND_LATLON]: 0, [KIND_ADDRESS]: 0, [KIND_POSTAL]: 0, [KIND_EMPTY]: 0 };
  for (const entry of classified || []) {
    if (counts[entry.kind] !== undefined) counts[entry.kind] += 1;
  }
  return counts;
}
