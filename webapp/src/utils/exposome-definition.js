export function resolveExposomeDefinition(exposomeId, expo, overrides = {}) {
  let resolvedOverrides = { ...overrides };
  if (
    expo.year_columns
    && !resolvedOverrides.column
    && expo.default_year
    && expo.year_columns[expo.default_year]
  ) {
    const year = expo.default_year;
    resolvedOverrides = {
      column: expo.year_columns[year],
      yearLabel: String(year),
      ...resolvedOverrides,
    };
  }
  return { id: exposomeId, ...expo, ...resolvedOverrides };
}
