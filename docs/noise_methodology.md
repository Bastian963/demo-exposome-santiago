# Noise layer (MMA Minuta Mapa de Ruido GSU 2023)

Commune-level environmental noise exposure for the Región Metropolitana
de Santiago, derived from the **MMA 2024 Minuta Mapa de Ruido Gran
Santiago Urbano 2023** (Ministerio del Medio Ambiente). The layer
summarizes population exposure to road-traffic noise above
internationally accepted thresholds (Lden ≥ 55 dB(A) and Ln ≥ 50 dB(A)),
following the European Environmental Noise Directive (END, 2002/49/EC)
methodology adopted by Chile for urban noise mapping.

## Why include noise

Chronic environmental noise is a well-established risk factor for
cardiovascular disease (ischemic heart disease, hypertension, stroke)
and is increasingly linked to **cognitive decline, sleep disruption
and dementia risk** in older adults (Carey et al. 2018; *Lancet
Commission on dementia prevention* 2020/2024). For the BrainLat exposome
this layer complements `sleep_context` and `air_quality` by providing
the chronic acoustic stressor that mediates part of the
traffic → sleep → cognition pathway.

## Regional reference values

- **MMA Minuta 2024** (resumen ejecutivo público, MMA 2024):
  - GSU-wide population exposed above Lden 55 dB(A): ~1.18 M people
    (~29% of the modelled area, depending on year).
  - GSU-wide population exposed above Ln 50 dB(A): ~0.89 M people
    (~22% of the modelled area).
  - Source: Minuta Mapa de Ruido Gran Santiago Urbano 2023, MMA 2024.
- **WHO Environmental Noise Guidelines for the European Region (2018)**:
  - Strong recommendation to reduce noise below **53 dB Lden** (road)
    and **45 dB Ln** (road) because of adverse health effects.
  - Chile's END-based thresholds (Lden ≥ 55, Ln ≥ 50) are slightly
    more permissive than WHO recommendations.

## Inputs

- `data/processed/santiago_noise_mma_2023.csv` — 52 communes × 7 cols.
  Source attribution table joined at commune level to the Santiago
  administrative boundaries.
- `data/processed/santiago_noise_mma_2023.geojson` — same content with
  commune polygons (EPSG:4326).
- `data/processed/santiago_noise_mma_2023_metadata.json` — provenance,
  thresholds, modelled perimeter, methodology notes.

## Pipeline

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_noise.py
python scripts/plot_noise_map.py
python scripts/build_master_exposome.py
```

The pipeline is **fully reproducible from the official MMA Minuta
table** (no GEE, no API). `run_noise.py` ingests the per-commune
exposure table published by MMA and joins it to the Santiago boundary
geojson. `plot_noise_map.py` produces a 4-panel figure (chloropleth
with hatched grey for non-modelled communes, ranked bar chart, NSE
correlation, and a summary panel).

## Metrics

All 52 communes × 7 columns. Columns:

- **`name`** — commune name (UTF-8, INE 2017 spelling).
- **`noise_ld_pop_exposed`** — population exposed above Lden 55 dB(A)
  (number of inhabitants; 0 for non-modelled communes).
- **`noise_ld_pct_exposed`** — % of commune population exposed above
  Lden 55. Range observed: 0 – 24.0% (Cerrillos).
- **`noise_ln_pop_exposed`** — population exposed above Ln 50 dB(A)
  (night-time). Range: 0 – 12 000.
- **`noise_ln_pct_exposed`** — % of commune population exposed above
  Ln 50. Range: 0 – 31.0% (Cerrillos).
- **`noise_combined_pct`** — union of (Lden ≥ 55 ∪ Ln ≥ 50) population
  share; used as the master ranking metric. Range: 0 – 26.0%.
- **`noise_in_gsu_map`** — binary flag (1 = commune is inside the GSU
  modelled perimeter, 0 = outside). 35 of 52 communes are modelled.

### Top 5 / bottom 5 by `noise_combined_pct`

- **Top 5** (highest exposure, central/pericentral): Cerrillos 26.0,
  Vitacura 26.0, Lo Espejo 24.5, Renca 20.5, Lo Barnechea 19.5.
- **Bottom 5** (all non-modelled, exposure = 0): Alhué, Buin, Calera
  de Tango, Colina, Curacaví — outside the GSU perimeter.

## Interpretation

The GSU (Gran Santiago Urbano) perimeter defined by the MMA Minuta
covers only the **35 urban communes** of Santiago city proper plus a
small set of contiguous urbanized communes. The remaining 17
communes (periurban + rural) are not noise-modelled and therefore
carry `noise_in_gsu_map = 0` with all exposure values set to 0 by
construction (see `metadata.note`). This is **not** a low-exposure
finding; it is a **structural coverage gap** that the layer documents
explicitly. Users analysing the regional exposome should treat
`noise_in_gsu_map = 0` as "no modelled estimate available" rather than
"exposure is zero".

The most exposed communes cluster in the urban core and along major
traffic corridors (Cerrillos near Pudahuel airport / Costanera Norte;
Vitacura near Av. Kennedy; Lo Espejo near Gran Av.; Lo Barnechea
near Av. Las Condes). Lo Espejo and Renca also show high exposure
despite lower commercial activity, consistent with cumulative road
traffic on the peripheral ring.

## Brain-health / exposome interpretation

- **Direct acoustic stress**: chronic Lden > 55 dB increases cortisol,
  impairs sleep architecture, and is associated with 8% higher
  dementia incidence per 10 dB increase (Carey 2018).
- **Sleep pathway**: night-time Ln > 50 dB is the strongest predictor
  of sleep disruption; `noise_ln_pct_exposed` overlaps conceptually
  with `sleep_context` but is sourced independently.
- **Cardiovascular pathway**: hypertension/IHD mediation suggests a
  vascular route to vascular dementia, partially independent of
  air-pollution co-exposure.
- **Socioeconomic confounding**: high-noise communes in Santiago are
  not exclusively poor (Vitacura has very high exposure yet high NSE)
  → adjust for NSE in any exposome model.

## Limitations

1. **Coverage gap**: only 35/52 communes modelled (GSU perimeter
   only). The 17 non-modelled communes (Alhué, Buin, Calera de Tango,
   Colina, Curacaví, El Monte, Huechuraba partial, Isla de Maipo,
   Lampa, María Pinto, Melipilla, Padre Hurtado, Paine, Peñaflor,
   Pirque, San José de Maipo, San Pedro, Tiltil, Talagante) are
   flagged `noise_in_gsu_map=0` with exposure = 0. Any aggregate
   statistic (e.g. RM-wide mean) **must** be restricted to the 35
   modelled communes, otherwise the mean is biased towards 0.
2. **Modelling horizon**: 2023 base year. The Minuta does not yet
   integrate 2024/2025 changes (Costanera Norte extension, EV fleet
   transition).
3. **Resolution**: commune-level aggregation, not 100 m grid. Within-
   commune heterogeneity (corridor vs quiet street) is hidden.
4. **No occupational noise**: only environmental (road-traffic)
   noise. Occupational exposure not captured.
5. **No aircraft noise separation**: Pudahuel/SCL airport noise is
   folded into the Lden/Ln estimate but not separated from road.
6. **WHO thresholds stricter**: MMA uses Lden ≥ 55 / Ln ≥ 50 (END
   baseline); WHO 2018 recommends 53 / 45. The layer over-states
   "safe" exposure by ~2–5 dB.

## Reproducibility

- Source: MMA 2024 Minuta Mapa de Ruido Gran Santiago Urbano 2023
  (publication date 2024, base year 2023).
- URL: https://mma.gob.cl/minuta-mapa-de-ruido-gran-santiago-2023
- Pre-processed table: `data/processed/santiago_noise_mma_2023.csv`
  (52 rows, deterministic, no network).
- Re-run: `python scripts/run_noise.py` (idempotent if input CSV
  unchanged).
- Random seeds: none (deterministic table-join).
- Cache: not required (no GEE, no API).
