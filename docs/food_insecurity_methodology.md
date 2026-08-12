# Food insecurity layer (CASEN SAE, 2020 & 2022)

Commune-level prevalence of **moderate-severe household food insecurity**
for the Región Metropolitana de Santiago, from official small-area
estimates published by Chile's Ministerio de Desarrollo Social y Familia
(MDSF). The layer measures **household experience** (whether people had
enough to eat), which complements — not duplicates — the `food_environment`
layer's measure of **retail supply** (supermarket density/distance from
OSM).

## Source

- **Publisher**: División Observatorio Social, Subsecretaría de Evaluación
  Social, Ministerio de Desarrollo Social y Familia (MDSF), with technical
  support from FAO.
- **Landing page**: https://observatorio.ministeriodesarrollosocial.gob.cl/inseguridad-alimentaria-2022
- **Methodological note**: "Nota Metodológica CASEN — Estimación de la
  prevalencia de hogares que experimentan inseguridad alimentaria moderada
  - severa a nivel comunal mediante metodología de estimación de áreas
  pequeñas (SAE)", June 2024. Archived at
  `data/raw/casen_food_insecurity/Nota_Metodologica_CASEN_Estimacion_de Inseguridad_Alimentaria_Comunal.pdf`.
- **Full technical report (FAO)**: "Estimation of the prevalence of
  moderate and severe food insecurity in Chilean municipalities using
  small area estimation methods", FAO, 2024.
  https://openknowledge.fao.org/items/6d37e6a2-2678-4566-bef3-125159230a60
- **Years available**: **2020 and 2022 only** — no other years have been
  published as of this writing (2026-07-07). 2020 estimates are based on
  CASEN 2020; 2022 estimates on CASEN 2022 (published 2024).
- **Raw files**: `data/raw/casen_food_insecurity/` (xlsx × 2 + PDF; small
  enough to keep versioned, see the folder's `README.md`).

## Indicator

**ODS/SDG 2.1.2**: prevalence of households experiencing moderate-severe
food insecurity, measured via the **Food Insecurity Experience Scale
(FIES)** — 8 dichotomous items asked of the household informant about the
last 12 months (worry about running out of food, inability to eat healthy/
varied food, skipped meals, going a full day without eating, etc.). FIES
has been included in CASEN since 2017.

Responses are fit to a **Rasch model**, which places each household on a
severity continuum and yields a **probability of food insecurity** rather
than a binary classification — this is a probabilistic, not dichotomous,
outcome (unlike the income-poverty indicator), which required methodological
adjustments (see below).

## Method: Small Area Estimation (SAE), Fay-Herriot

CASEN is not designed to be representative at the commune level (Chile's
smallest administrative unit) — direct commune estimates from the survey
alone would be too imprecise. Since 2011 MDSF has produced **SAE estimates**
for income poverty (and since 2015 for multidimensional poverty); in
2023-2024, in a technical cooperation program with FAO, this was extended
to food insecurity.

**Fay-Herriot area-level model**: the final SAE estimate for each commune
is a variance-weighted linear combination of a **direct estimate** (from
CASEN, for communes with sufficient sample) and a **synthetic estimate**
(regression on commune-level administrative covariates, applied to all
communes):

```
θ̂_FH = γ̂ · θ̂_direct + (1 − γ̂) · θ̂_synthetic
```

where `γ̂ = σ̂²_u / (σ̂²_u + ψ̂²_d)` — the weight given to the direct
estimate grows as its sampling variance shrinks relative to the random-
effect variance. Implemented in R with the `EMDI` package (Estimating and
Mapping Disaggregated Indicators) since 2020.

**Adjustments specific to food insecurity** (vs. the income-poverty SAE
pipeline):
1. **Two-component variance**: because the FIES/Rasch outcome is a mean of
   probabilities (not a 0/1 poverty indicator), direct-estimate variance
   must combine (a) sampling error from the survey design and (b) Rasch
   measurement error.
2. **Weight trimming (Potter 1993) done in two Rasch passes**: (i) fit
   Rasch without expansion factors to get sample-level probabilities, (ii)
   trim commune sampling weights (32 region × area groups, threshold `K`
   minimizing MSE) using those probabilities as the response, (iii) refit
   Rasch **with** the trimmed weights to produce the probabilities actually
   used in direct/SAE estimation.
3. **Commune inclusion criteria** were adapted from the poverty pipeline:
   the criterion on observed poverty count is dropped (not applicable to a
   probability mean), and design effect (DEFF) is replaced by the
   **intraclass correlation (ρ)**. A commune enters the Fay-Herriot direct/
   synthetic blend if it has ≥14 degrees of freedom, or (if <14) sample
   size ≥50 AND df >2 AND ρ ≥ ρ_min. Communes failing these get a
   **synthetic-only** estimate (regression prediction, no direct CASEN
   contribution).
4. Final steps common to all SAE indicators: variance via Generalized
   Variance Function, confidence intervals from Mean Squared Error (MSE),
   regional benchmarking (calibration so commune totals reconcile with
   regional CASEN estimates), and model validation.

### Communes using synthetic-only estimates (data-quality caveat)

| Year | Communes in Casen sample | Meeting inclusion criteria (Fay-Herriot) | Synthetic-only |
|------|---------------------------|-------------------------------------------|-----------------|
| 2020 | 324 / 346 | 283 | 41 |
| 2022 | 335 / 346 | 306 | 29 |

The published xlsx flags each commune's `Tipo de estimación SAE` as
`"Directa y Sintética (Fay-Herriot)"` or `"Sintética"` — this column is
preserved in the processed output (`food_insec_sae_type_2020` /
`_2022`) so synthetic-only estimates can be filtered or flagged downstream.

## RM coverage (verified during ingestion)

All **52 communes of the Región Metropolitana have a non-missing estimate
in both years** — no suppression. The 7 communes suppressed in the 2022
release for failing statistical quality criteria (Camiña, Colchane,
Ollagüe, Río Verde, Camarones, Putre, General Lagos) are all **outside the
RM**; their synthetic fallback values are listed separately in the 2022
workbook's `Hoja1` sheet but are not needed for this project's scope.

Observed range (2022): Vitacura 1.2% (lowest) to La Granja 30.0%
(highest). 2020: Vitacura 3.4% to La Pintana 30.5%.

## Relationship to the `food_environment` (OSM) layer

These two layers measure **different constructs** and are intentionally
kept as **separate exposome layers**, not merged:

| | `food_insecurity` (this layer) | `food_environment` (OSM) |
|---|---|---|
| Measures | Household **experience** (FIES/Rasch probability) | Retail **supply** (supermarket density/distance) |
| Source | CASEN survey, official SAE | OpenStreetMap crowdsourced tags |
| Temporal | 2 static years (2020, 2022), no slider | Single 2024-2025 OSM snapshot |
| Known limitation | Synthetic-only estimate in some communes; household- not person-level | Structural OSM coverage gap: unhealthy retail categories are empty (see `docs/food_environment_methodology.md`) |

Empirically, the two layers are essentially **uncorrelated** (Spearman
ρ = -0.04 between `food_insec_2022` and `food_index`, n=52) — food
insecurity is driven primarily by income/affordability, not physical
proximity to retail, so `food_index`'s supermarket-density-and-distance
signal carries almost no information about whether households actually
have enough to eat. This is direct evidence the two layers are
complementary, not redundant: `food_insecurity` correlates moderately
with socioeconomic position instead (ρ = -0.42 vs. `nse_index_pca`).

## Output columns

`data/processed/santiago_food_insecurity.csv` (52 rows):

- **`name`** — commune name (canonical, matches other exposome layers).
- **`food_insec_2020`** — % of households in moderate-severe food
  insecurity, CASEN 2020 SAE estimate.
- **`food_insec_ci_low_2020` / `food_insec_ci_high_2020`** — 95% CI bounds (%).
- **`food_insec_sae_type_2020`** — `"directa_sintetica"` (Fay-Herriot
  blend) or `"sintetica"` (synthetic-only, no direct CASEN contribution).
- **`food_insec_2022` / `_ci_low_2022` / `_ci_high_2022` / `_sae_type_2022`** — same, CASEN 2022.
- **`food_insec_change`** — `food_insec_2022 − food_insec_2020`, in
  percentage points. Positive = worsened.

Primary column for the webapp/master table: **`food_insec_2022`** (most
recent year).

## Limitations

1. **Only two time points** (2020, 2022) — no annual trend, no time
   slider in the webapp (`has_annual: false`).
2. **Household-level, not person-level**: the published indicator is the
   share of *households*, not individuals; larger low-income households
   are not weighted differently.
3. **Synthetic-only estimates** in a minority of communes each year (see
   table above) rely entirely on administrative covariates, not direct
   CASEN observation for that commune — wider uncertainty, flagged via
   `food_insec_sae_type_*`.
4. **Not comparable across years at the household-composition level**:
   2020 CASEN was fielded under COVID-19 conditions (Chile's confinement
   period), which may affect food-insecurity responses independent of any
   underlying trend — treat `food_insec_change` as indicative, not a
   clean panel comparison.
5. **No sub-commune resolution**: SAE estimates are only produced at
   commune level (`resolution: comuna`, `has_fine_layer: false`).

## Reproducibility

- Raw inputs are versioned in the repo (`data/raw/casen_food_insecurity/`,
  no API key, no network access needed to reproduce).
- Pipeline: `python scripts/run_food_insecurity.py`
  (`src/exposome/food_insecurity.py`).
- Random seeds: none (deterministic read of the published xlsx).
