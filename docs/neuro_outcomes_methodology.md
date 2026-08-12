# Neuro-sanitary outcome comparators

This project treats DEIS mortality and hospital discharge files as external
ecological outcome comparators, not as exposome layers. They are kept outside
the master exposome table and are used to test whether commune-level exposome
patterns align with public neuro-sanitary outcomes.

## Mortality comparator

- Source: DEIS mortality export in `data/raw/deis/defunciones/`.
- Current window: 2018-2022.
- Unit: commune of residence/registration available in the DEIS export.
- Main outcomes:
  - dementia: `F00-F03` and `G30`
  - Alzheimer: `G30`
  - cerebrovascular disease: `I60-I69`
  - parkinsonism: `G20-G21`
- Metrics: total deaths, crude rate per 100,000, age-adjusted rate per
  100,000, age-specific rates, low-count flag.

Mortality is strongest for neurological outcomes that plausibly appear as a
cause of death. It is weak for common non-fatal mental health outcomes such as
anxiety, depression and psychosis.

## Hospitalization comparator

- Source: ten DEIS hospital-discharge ZIPs under `data/raw/deis/egresos/`,
  covering 2011–2020.
- Unit: discharge episode assigned to commune of residence, not a unique
  patient.
- Spatial support: the 52 communes of the Región Metropolitana.
- Denominator: official INE commune estimates/projections, base Censo 2017,
  matched by year, sex and single year of age.
- Harmonized strata: sex (`male`, `female`, plus an explicit unknown category)
  and nine age bands (`0–9`, `10–19`, …, `80+`). Decadal bands avoid the
  invalid 65-year split created by the coarser DEIS labels in most years.
- Diagnostic families: all cause plus mental/behavioural, neurological,
  cardiovascular and lower-respiratory ICD-10 groups declared in
  `src/exposome/hospitalization_analytics.py`.

The reader streams the CSV member inside each ZIP in bounded chunks. It never
extracts or writes individual episodes; only a commune × year × sex × age ×
outcome cube is persisted. The full audit found 16,268,949 national rows,
6,216,376 RM rows and all 52 expected RM commune codes. There was one missing
primary diagnosis among the eligible RM rows, 107 records with unknown sex and
305 missing/extreme length-of-stay values; all are retained or excluded under
explicit rules in the QC JSON.

### Analysis windows

The years serve different purposes and must not be pooled without a label:

| Window | Years | Purpose |
|---|---|---|
| Primary chronic | 2018–2019 | Pre-COVID commune comparison with antecedent PM2.5 (2000–2017) |
| Chronic sensitivity | 2018–2020 | Quantify sensitivity to the COVID disruption |
| Trend | 2011–2019 | Descriptive pre-COVID time series |
| Annual panel | 2015–2019 | Commune and year fixed effects |
| Panel sensitivity | 2015–2020 | Adds 2020, always labelled as COVID sensitivity |

For every window, observed counts are compared with expected counts calculated
from RM-wide year × sex × age-specific reference rates. The main commune metric
is the standardized morbidity ratio (SMR); crude rates and population
person-years remain available for inspection.

### Exposome association models

The primary chronic model is a negative-binomial count regression with
`log(expected)` as offset. It estimates the rate ratio per one standard
deviation of exposure and adjusts for `nse_index`; primary-care facility count
is a sensitivity covariate. Benjamini–Hochberg FDR is applied separately to the
cardiorespiratory and neuropsychiatric arms. Queen-contiguity Moran's I with 999
permutations tests residual spatial structure.

The annual model is Poisson PPML with commune and year fixed effects,
`log(expected)` offset and standard errors clustered by commune. Available
year-matched inputs currently cover precipitation consecutive dry days and
wildfire burned area. Annual heat is intentionally reported as unavailable:
the canonical heat layer now requires ERA5-Land, while the existing 2015–2019
Open-Meteo grid caches are a retired spatial product and are not silently mixed
into the model.

### First-pass findings (2026-07-18)

These estimates establish that the files are analytically useful, but they are
not causal results.

- Historical PM2.5 had an SD of 2.435 µg/m³. Per SD, the primary model estimated
  RR 1.146 (95% CI 1.064–1.235; FDR q=0.009) for cardiovascular admissions,
  RR 1.143 (1.048–1.247; q=0.018) for respiratory admissions and RR 1.134
  (1.083–1.187; q<0.001) for cerebrovascular admissions. COPD and all mental
  admissions did not pass FDR. Estimates were similar after adjustment for
  primary-care facility count.
- Greenness was inversely associated with cardiovascular, respiratory and
  cerebrovascular admissions in the exploratory sweep. Several urban access
  indices were positively associated with cerebrovascular admissions; their
  direction is compatible with residual urbanicity, referral/access and coding
  differences and should not be read as harmful effects of access.
- Residual spatial autocorrelation remained for the PM2.5 cardiovascular,
  respiratory, COPD and mental models (permutation p<0.05). Therefore their
  non-spatial confidence intervals are screening results; a spatial BYM2 or
  equivalent model is required before publication. The cerebrovascular PM2.5
  residual Moran test was not significant (p=0.069).
- No precipitation or wildfire panel estimate passed arm-wise FDR. The nominal
  respiratory/precipitation result after adding 2020 had p=0.027 but q=0.162,
  so it is not evidence after multiple-testing correction.
- 2020 is a strong utilization/coding shock: compared with 2019, all-cause
  discharges fell to 81.6%, respiratory to 45.9%, COPD to 43.7%,
  cerebrovascular to 85.8% and mental admissions to 75.7%. This validates the
  decision to keep 2020 out of the primary window.

### Reproduction and outputs

From the repository root:

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/run_hospitalization_exposome_analysis.py
```

Main local artifacts:

- `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/`:
  source inventory, QC, completed cube, annual expected counts, window SMRs,
  metadata and manifest.
- `data/processed/cl/santiago/santiago_communes/analysis/hospitalizations/`:
  chronic and panel model tables, exposure matrices and Moran diagnostics.
- `figures/analysis/hospitalizations/`: trend and PM2.5 forest plots.

Raw and generated data artifacts are intentionally ignored by Git; their
tracked READMEs, code and configurations make them reproducible locally.

## Interpretation and limitations

- These data are suitable as an **outcome layer for ecological analysis**, not
  as an exposome and not for individual inference.
- A row is an episode, so recurrent admissions and transfers can contribute
  multiple records. The public export has no patient identifier for
  deduplication.
- Admissions reflect disease, access, referral pathways, bed supply, coding and
  healthcare-seeking. Adjustment for facility count is only a partial check.
- Exposure and outcome supports are commune-level; spatial misalignment,
  migration and within-commune heterogeneity remain.
- Several exploratory exposomes use different source periods. Only historical
  PM2.5 has a clearly antecedent primary interpretation here.
- Residual spatial autocorrelation, only 52 communes and multiple comparisons
  limit frequentist inference. Spatial hierarchical modelling and external
  validation are the next analytical steps.
- The COVID year is not comparable with routine pre-pandemic utilization and
  is used only in explicitly labelled sensitivity outputs.
