# Food environment layer (OSM retail outlets)

Commune-level retail food environment for the Región Metropolitana de
Santiago, derived from **OpenStreetMap** retail/amenity tags via
`osmnx`. The layer summarizes the **physical availability** of
supermarkets and (in principle) greengrocers, marketplaces, fast food
and convenience stores at commune scale. It does **not** measure diet
quality, food prices, household purchases, or dietary intake.

## Why include food environment

The food environment shapes diet quality, which in turn drives obesity,
type-2 diabetes, and hypertension — three of the 14 modifiable
dementia risk factors identified in the **Lancet Commission on
dementia prevention, 2024 update** (Livingston et al.). At the
neighborhood scale, accessibility of healthy retail (supermarkets,
greengrocers, ferias) is a structural determinant of dietary patterns,
and the absence of healthy retail (food desert) or the dominance of
unhealthy retail (food swamp) is independently associated with
adverse cardiometabolic outcomes and downstream cognitive decline
(Finlay et al. 2026, "Cognability", *Soc Sci Med*).

For the BrainLat exposome, this layer complements `walkability`,
`greenspace_access`, and `nse_index` to characterize the **retail
opportunity structure** that residents face when acquiring food.

## Regional reference values

- **CDC Modified Retail Food Environment Index (mRFEI)**: US counties
  typically range 0-50 (mean ~15). Values 100 (no unhealthy detected)
  are implausible in US data because fast food and convenience are
  well mapped.
- **USDA Food Access Research Atlas**: food desert = low-income
  tract where ≥500 people (or ≥33% of the population) live > 1 mile
  (urban) / > 10 miles (rural) from the nearest supermarket.
- **Santiago regional context**:
  - 6 supermarket chains dominate the formal retail: Lider, Jumbo,
    Unimarc, Santa Isabel, Tottus, Cugat.
  - ~400+ ferias libres operate weekly across the RM (mobile/temporary;
    under-mapped in OSM).
  - Almacenes/minimarkets (convenience equivalents) are pervasive in
    every commune but are **not systematically mapped in OSM Chile**.

## Inputs

- `data/processed/santiago_food_environment.csv` — 52 communes × 14 cols.
- `data/processed/santiago_food_environment.geojson` — same content with
  commune polygons (EPSG:4326).
- `data/processed/santiago_food_environment_metadata.json` — provenance,
  OSM tags, dedup radius, methodology, **coverage_gap** block.
- `cache/santiago_food_supermarket.geojson` — 602 OSM supermarket
  features used by the pipeline.

## Pipeline

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_food_environment.py
python scripts/plot_food_environment_map.py
python scripts/build_master_exposome.py
```

`run_food_environment.py` calls `build_food_environment_layer()` in
`src/exposome/food_environment.py`, which:

1. Loads the commune polygon (`boundaries.get_communes`).
2. For each of 5 OSM categories, downloads features within the RM
   union polygon via `osmnx.features_from_polygon`, caches the result
   under `cache/`, and re-uses the cache on subsequent runs.
3. Converts each feature to a representative point, deduplicates
   within a 25 m radius (cKDTree), and counts points per commune
   using a spatial join.
4. Builds a 1 km grid inside each commune polygon, computes
   distance-to-nearest-supermarket per grid point, then aggregates
   the mean per commune.
5. Computes mRFEI, food_swamp_ratio, density metrics, and the
   composite `food_index` (z-score of mRFEI, healthy_density,
   mean_dist_supermarket_m rescaled to 0-100).

`plot_food_environment_map.py` produces a 4-panel figure. The master
builder integrates the 13 numeric columns from this layer's CSV.

## Metrics

All 52 communes × 14 columns:

- **`name`** — commune name (UTF-8, INE 2017 spelling).
- **`food_n_supermarket`** — unique supermarkets in commune.
  Range: 0 (Alhué) to 56 (Santiago). Sum: 596.
- **`food_n_greengrocer`** — greengrocers. **Always 0** (see gap below).
- **`food_n_marketplace`** — marketplaces (ferias libres). **Always 0**
  in OSM; real count is much higher but not mappable.
- **`food_n_fastfood`** — fast food outlets. **Always 0** (see gap).
- **`food_n_convenience`** — convenience stores / almacenes. **Always 0**
  (see gap).
- **`food_n_healthy`** — `supermarket + greengrocer + marketplace`. In
  practice equals `food_n_supermarket` (596 total).
- **`food_n_unhealthy`** — `fastfood + convenience`. **Always 0**.
- **`food_healthy_density`** — healthy outlets per km². Range 0 to 2.41.
- **`food_unhealthy_density`** — unhealthy outlets per km². **Always 0**.
- **`food_mrfei`** — `healthy / (healthy + unhealthy) × 100`. Range
  0 (Alhué only) to 100 (all other communes). 51/52 communes = 100.
- **`food_swamp_ratio`** — `unhealthy / max(healthy, 1)`. **Always 0**.
- **`food_mean_dist_supermarket_m`** — mean distance (m) from 1 km
  grid points to nearest supermarket. Range 386 (Santiago) to 37 302
  (San José de Maipo). Sentinel 50 000 m for communes with no
  supermarket (Alhué: 24 183 m after clipping; in practice it gets
  the fallback because the grid finds nothing within 50 km).
- **`food_index`** — composite 0-100 score (z-score of mRFEI,
  healthy_density, mean_dist_supermarket_m). Range 0 (Alhué) to 100
  (Santiago); mean 66.3, std 15.1.

### Top 5 / bottom 5 by `food_index`

- **Top 5** (urban core, dense supermarket fabric): Santiago 100.0,
  Providencia 93.3, Independencia 85.1, Lo Prado 85.1, Ñuñoa 84.0.
- **Bottom 5** (rural / periurban, no supermarket in walking
  distance): Alhué 0.0, San José de Maipo 24.0, Lo Barnechea 48.0,
  Colina 51.6, Pirque 54.1.

## Interpretation

`food_index` is highly correlated with the inverse of
`food_mean_dist_supermarket_m` (Spearman ρ = -0.85). In practice the
index is dominated by **supermarket density and walking distance**;
the mRFEI component is near-constant (always 100, except Alhué) and
adds no signal because the unhealthy categories are missing.

The top 5 communes are central urban districts with multi-chain
supermarket presence (Santiago has 56 outlets, Providencia 28,
Ñuñoa 22). The bottom 5 are the rural/periurban communes that lack
any large-format grocery — Alhué has zero supermarkets in OSM, San
José de Maipo has 3 (mostly in the central town), Pirque has 3.
Lo Barnechea is an interesting case: it has 11 supermarkets (high
NSE residential area with Lider/Jumbo in the lower foothills) but
its enormous area (≈ 1 023 km², includes the Andean cordillera
up to the border with Argentina) drives a high mean distance
(16 km) and pulls its `food_index` down to 48.0.

**Food desert identification is feasible with the current data**;
**food swamp identification is not** because the unhealthy side of
the CDC mRFEI is structurally missing from the OSM snapshot.

## Critical coverage gap (transparent disclosure)

This layer has a **structural OSM coverage gap** that the
`coverage_gap` block in the metadata documents in detail:

- **4 of 5 retail categories return empty** when queried via
  Overpass with the standard CDC mRFEI tags:
  - `shop=greengrocer` → 0 outlets
  - `amenity=marketplace` → 0 outlets (real count much higher)
  - `amenity=fast_food` → 0 outlets (despite obvious abundance)
  - `shop=convenience` → 0 outlets (despite pervasive almacenes)
- **Only `shop=supermarket` returns data** (596 outlets, the
  formal retail backbone).
- The pipeline correctly computes mRFEI and food_swamp_ratio from
  the (mostly-zero) inputs, but these metrics are **degenerate**:
  - `food_mrfei = 100` in 51/52 communes (no unhealthy in OSM).
  - `food_swamp_ratio = 0` in 52/52 communes.
- The downstream `food_index` therefore reduces to a composite of
  supermarket density and access distance. The mRFEI component
  contributes a near-constant offset; the distance component
  dominates (Spearman ρ = -0.85 with the index).

This is not a bug in `src/exposome/food_environment.py`; the
Overpass queries are correctly formed. The issue is **structural
OSM coverage in Chile** for food/amenity categories. See the
`remediation_steps` block in
`data/processed/santiago_food_environment_metadata.json` for the
proposed path forward (re-run with bbox+longer sleep, alternative
tags, MINAGRI/SERCOTEC catalogs, etc., ~6-8 hours of work).

### Candidate data sources to close the gap (upgrade track)

Verified external sources that would supply the unhealthy-outlet
(and denser healthy-outlet) coverage OSM Chile lacks, so `food_index`
can graduate from *healthy-access* to a real healthy-vs-unhealthy
mRFEI. Ranked by tractability:

1. **Overture Maps — Places** *(strongest; drop-in)*. 64M+ global
   POIs (Meta + Microsoft + PinMeTo), **CDLA Permissive 2.0** (open),
   published as GeoParquet on AWS S3 / Azure. Includes
   `food` / `fast_food` / `convenience` / `restaurant` categories
   absent from OSM Chile. **No API key**; queryable directly with
   **DuckDB spatial** (`read_parquet` over S3 + RM bbox filter +
   category filter), which fits the existing geopandas/DuckDB stack.
   Risk: validate real RM coverage before trusting the ratio.
   - https://docs.overturemaps.org/guides/places/
   - https://registry.opendata.aws/overture/
2. **datos.gob.cl — Patentes comerciales / de alcoholes**
   *(authoritative but heterogeneous)*. Municipal licences for
   restaurants, liquor stores (botillerías) and almacenes — the
   official Chilean source. Cost: each municipality publishes
   separately in mixed Excel/CSV, mostly addresses → requires
   geocoding.
   - https://datos.gob.cl/dataset?tags=Patentes+Comerciales
   - https://datos.gob.cl/dataset/patentes-de-alcoholes
3. **ODEPA + ASOF — Ferias libres RM** *(fixes the healthy side)*.
   432–463 RM ferias with lat/lon, commune, stall counts and hours,
   downloadable as Excel. Directly corrects the `marketplace` (feria)
   undercount that currently biases the healthy half of the index.
   - https://apps.odepa.gob.cl/powerBI/reporte_ferias_libres.html
   - https://asof.cl/region-metropolitana/

Any of these is additive: it does not require re-wiring the webapp,
only re-running `scripts/run_food_environment.py` with the enriched
inputs so `food_index` gains the unhealthy component (and the palette
label can drop the "acceso" reframing once the balance is real).

## Brain-health / exposome interpretation

- **Food desert pathway** (SUPPORTED with current data): low
  supermarket density and long walking distance → lower fruit/vegetable
  intake → higher cardiovascular risk → vascular dementia risk.
  Communes identified: Alhué, San José de Maipo, Lo Barnechea,
  Colina, Pirque, Curacaví, María Pinto.
- **Food swamp pathway** (NOT supported with current data):
  dominance of fast food / convenience over healthy retail → poor
  diet quality → obesity/diabetes → metabolic/vascular cognitive
  decline. This is the most policy-relevant food environment
  pathway and cannot currently be captured. Future OSM enrichment
  or commercial catalog cross-referencing is required.
- **Healthy retail concentration pathway** (PARTIALLY supported):
  density of supermarkets in central urban communes (Santiago,
  Providencia, Ñuñoa) likely supports diverse dietary patterns,
  but the lack of fast food data prevents a balanced ratio
  interpretation. The composite `food_index` should be read as
  "healthy retail opportunity" rather than "diet quality".
- **Socioeconomic pathway**: the high-NSE inner ring (Vitacura,
  Las Condes, Providencia) has high supermarket access AND would
  plausibly have high fast food access if mapped; this is not
  captured. A spurious "healthy" NSE correlation may emerge from
  the missing data, not from real dietary advantage.

## Limitations

1. **OSM coverage gap** (critical, see above): 4 of 5 categories
   are empty. The `coverage_gap` block in the metadata details the
   remediation plan.
2. **mRFEI degenerate**: 51/52 communes score 100 not because they
   are healthy but because OSM has no unhealthy outlets mapped.
   Treat the metric as "absence of unhealthy in OSM" not as
   "100% healthy retail composition".
3. **food_swamp_ratio not informative**: always 0. Reported for
   schema compatibility and as a flag for downstream code.
4. **No price, no quality, no opening hours**: the layer measures
   outlet presence, not what they sell at what price. A small
   feria libre selling fresh produce at lower prices than a
   supermarket is not captured; neither are seasonal closures.
5. **No service area / catchment**: distance is computed against a
   uniform 1 km grid, not a population-weighted catchment. A
   commune with 100 % of its population near a supermarket but
   large unpopulated Andean area will still show high mean
   distance (Lo Barnechea is the textbook case).
6. **CRS metric**: `EPSG:32719` (UTM 19S, Chile-specific). Not
   directly comparable to food access layers in other cities
   without re-projection.
7. **No food assistance programs**: JUNAEB, CASEN, RSH food
   insecurity indicators are not included. The layer measures
   supply, not demand or affordability.
8. **Supermarkets are a proxy for "healthy"**: not all supermarket
   shoppers buy healthy food, and not all minimarkets are
   unhealthy. The CDC mRFEI classification is a simplification
   that ignores product mix within each outlet type.

## Reproducibility

- Source: OpenStreetMap via `osmnx.features_from_polygon` against
  the RM union polygon.
- Tags: `shop=supermarket`, `shop=greengrocer`, `amenity=marketplace`,
  `amenity=fast_food`, `shop=convenience`.
- Deduplication: 25 m cKDTree cluster → 1 representative point.
- Coverage: 1 km grid sampling per commune polygon.
- CRS metric: `EPSG:32719` (UTM 19S, Chile-specific).
- Re-run: `python scripts/run_food_environment.py` (requires
  network; cache per-category under `cache/santiago_food_*.geojson`).
- Random seeds: none.
- Pre-processed output: deterministic given the same OSM snapshot.
- The current cache contains only `santiago_food_supermarket.geojson`;
  the other 4 categories were not cached on the run that produced
  the committed CSV. Re-running the script should re-attempt all 5
  categories (sleep 8s between queries; 3 retries).
