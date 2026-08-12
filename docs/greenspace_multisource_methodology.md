# Greenspace multi-source layer — methodology

Layer id: `greenspace_multisource` · City: Santiago (52 comunas RM) · Source: Google
Earth Engine (`exposome-api`).

## Why this layer exists

Single sources each undercount urban green in a different way. This layer combines
two peer-reviewed global products so that what one source misses another catches,
and makes the reconciliation explicit rather than reporting three unrelated green
numbers.

| Source | What it measures | Gap it closes | Key limitation |
|---|---|---|---|
| OpenStreetMap (`greenspace_access`) | Designated parks / plazas + access distance | — (reference) | Misses street trees and informal/low green (~most street-visible vegetation is not in OSM) |
| **Dynamic World V1** (10 m) | Total vegetated cover (trees + grass + shrub), incl. lawns and informal green | Informal / low green OSM never maps | 10 m argmax assigns one class per pixel, so isolated street trees are not counted as green |
| **Meta/WRI Canopy Height** (1 m) | Street-tree canopy cover + height | Street trees OSM and the 10 m argmax both miss | Reliable only aggregated (>=30 m); no per-pixel claim |

**Complement status — not yet validated.** The intended evidence is per-scene
recall of DW + canopy vs. hand-drawn `vegetation` labels
(`scripts/greenspace_multisource_sanity_check.py`, 36-scene worklist); annotation
is pending (0/36), so the complement is *machinery-in-place*, not confirmed. What
is already measurable and non-tautological is the **dense-urban** story: in the
compact urban core (Santiago, Independencia, Estación Central, Ñuñoa …) Dynamic
World's 10 m argmax reads ~0–1 % green, yet ≥3 m tree canopy is 5–19 %, so the 1 m
canopy recovers street trees both OSM and the 10 m argmax miss. (Across *all* 52
communes canopy also exceeds OSM green, but that aggregate is inflated by rural
communes where OSM simply maps no parks — it is not the street-tree signal.)

## Data sources

- **Dynamic World V1** — `GOOGLE/DYNAMICWORLD/V1`, near-real-time 10 m land-cover
  class probabilities (9 classes). Peak Southern-Hemisphere greenness season
  (Oct–Mar) of the configured year(s).
- **Meta/WRI Global Canopy Height** — `projects/meta-forest-monitoring-okw37/assets/CanopyHeight`,
  1 m canopy height. Band `cover_code` is canopy height in **integer metres**
  (empirically 0–~30 in the RM; 0 == no canopy), confirmed by histogram and by the
  expected park-vs-dense-block gradient (Cerro San Cristóbal ~58 % cover, downtown
  ~12 %).

## Metric definitions

Configured in `config/cities/santiago.yaml` under `greenspace.dynamic_world` and
`greenspace.canopy`.

**Dynamic World (argmax fractional cover — the Dynamic World convention).** The
seasonal composite is the per-class **mean** probability. A pixel's dominant class
is its argmax; a pixel is *green* when the strongest green-class probability
exceeds every non-green-class probability. This argmax is computed with cheap
per-band `max` reducers on the single mean image — a per-pixel `arrayArgmax` over
the ~85-image stack times out GEE at regional scale.

- `green_total_pct` — % of pixels whose dominant class ∈ {trees, grass, shrub_and_scrub}.
- `tree_pct` — % of pixels whose dominant class == trees.
- `grass_pct` — % of pixels whose dominant class == grass.

`crops` and `flooded_vegetation` are **excluded** from green: peri-urban
agriculture is not health-relevant urban greenspace.

**Meta canopy.**

- `canopy_cover_pct` — % of pixels with canopy height ≥ `min_height_m` (**3 m**).
  The 3 m threshold was chosen from a sensitivity sweep: at ≥1 m even dense
  downtown reads ~27 % "canopy" (re-detecting the 1–2 m shrubs Dynamic World
  already sees, and near the product's ~2.8 m MAE noise floor); ≥3 m isolates
  genuine tree canopy while the dense-urban complement (canopy > DW-green) still
  holds. `≥5 m` is a stricter alternative that also preserves the complement.
- `canopy_mean_height_m` — mean canopy height over the commune (0 counted as no canopy).

## Spatial aggregation and scale

- Commune metric: zonal mean over each of the 52 comunas. Dynamic World is reduced
  at **30 m** and canopy at **30 m**. 30 m is used, not 10 m, because reducing 85
  seasonal images at 10 m over the giant Andean communes (San José de Maipo
  ~5 000 km²) exceeds GEE's interactive compute budget, and a commune **mean** is
  unbiased under 30 m subsampling. Sampling the 1 m canopy at 30 m also directly
  honors that product's "reliable only when aggregated (≥30 m)" guidance.
- Compute CRS `EPSG:32719`; output CRS `EPSG:4326`.
- Fine sub-commune layer: `scripts/export_webapp_green_subcomuna.py` builds one
  AOI-wide, metric-CRS-aligned 1 km grid and computes the **real** Dynamic World
  green fraction per cell from the 10 m source using 30 m analytical sampling.
  Administrative limits only clip/display or summarize that stable grid; they do
  not reset its phase. Output
  `data/processed/<iso2>/<city>/<study>/subcomuna/green.geojson` (replaces the former synthetic
  placeholder). This is what `has_fine_layer: true` serves in the webapp.

## Outputs

- `data/processed/santiago_greenspace_multisource.csv` / `.geojson` / `_metadata.json`
- `figures/greenspace_multisource_santiago_2panel.png`
- Merged into the exposome master as `green_total_pct`, `tree_pct`, `grass_pct`,
  `canopy_cover_pct`, `canopy_mean_height_m` (webapp `green` layer → `green_total_pct`).

## Limitations

- Dynamic World's 10 m argmax does not count isolated street trees as green in
  dense blocks — this is precisely why the 1 m canopy layer is included; the two
  are complementary, not redundant.
- Meta canopy is trustworthy only aggregated (≥30 m); values here are commune /
  1 km-cell means, never per-pixel.
- Dynamic World can confuse **bare soil and sparse/dry vegetation** in semi-arid
  peri-urban terrain (Santiago's northern fringe), and `green_total_pct` in rural
  communes is dominated by `shrub_and_scrub` (Mediterranean matorral). Whether
  shrub inclusion over-counts "green" there is assessed in the annotation
  sanity-check (`docs/greenspace_cv_approval_checklist.md`).
- Single peak-season snapshot; inter-annual variability not captured
  (`has_annual: false`).
- **Known per-unit annual gap — Bogotá / Los Mártires / 2019.** The Dynamic World
  seasonal composite (Oct–Mar) has zero valid pixels for this one locality in this
  one year only; `green`/`tree`/`grass` come back `NaN` from GEE deterministically
  (confirmed against the cached zonal stats, reproduced twice). All other 19
  Bogotá localidades and all other 8 configured years (2016–2018, 2020–2024) are
  complete. Not a code or cache bug, not fixed by retrying — Los Mártires (6.5 km²)
  is not even the smallest locality (Candelaria at 2.1 km² and Antonio Nariño at
  4.9 km² both have valid, non-zero data for 2019), so this reads as a genuine
  cloud-cover/imagery-availability gap for that specific geometry + season +
  year, not an area-size artifact. Accepted as a known, permanent gap rather than
  interpolated or worked around: `run_missing_annual_exposomes.py --study
  bogota_localidades --status` will always show `greenspace_multisource: 8
  complete / 1 pending`, and `--require-complete` will always fail on it. This is
  expected — do not spend further time retrying or debugging this specific cell
  before checking this note.

## Reproduce

```bash
.venv/bin/exposome run --study santiago_communes --layers greenspace_multisource --resume
.venv/bin/python scripts/export_webapp_green_subcomuna.py --study santiago_communes
.venv/bin/python scripts/build_master_exposome.py
.venv/bin/python scripts/export_webapp_master.py
```

`dynamic_world`/`canopy` settings live in `config/layers/greenspace.yaml` (composed for
every study by `config.load_config`); `config/cities/santiago.yaml` no longer defines
them, so any direct invocation must resolve through a study id (`santiago_communes`),
not the bare legacy `santiago` city name.
