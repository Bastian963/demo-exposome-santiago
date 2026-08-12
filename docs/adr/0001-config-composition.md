# ADR 0001: Compose settings by layer, country, location and study

## Decision

Runtime settings use this precedence: layer defaults, country overrides,
location overrides and study overrides.  City YAML files are not shared defaults.

The schema is validated by strict dataclasses/loaders.  Legacy Santiago settings
remain behind an adapter only until the v3.0 parity gates pass.

## Consequences

- Buenos Aires cannot inherit a Chilean city configuration.
- Global providers remain reusable while national providers are explicit.
- New runner code receives a resolved Study context rather than selecting a city
  through an environment variable.
