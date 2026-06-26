# AGENTS.md — BrainLat Exposome Demo

High-signal guidance for agents working in this repo.

## Environment (critical)

Use the **new** `exposome` environment (Python 3.12) for all new work. Do NOT use the old `demo-exposome` / `brainlat` env (Python 3.11).

```bash
# Create if missing
mamba env create -f environment.yml

# Activate
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome

# Verify GEE
python -c "import ee; ee.Initialize(project='exposome-api'); print('GEE OK')"
```

If GEE auth fails, run `earthengine authenticate` inside the activated env and complete OAuth in browser.

Jupyter kernel: select **"Python 3.12 (exposome)"**. Reinstall with:
```bash
mamba run -p .conda/envs/exposome python -m ipykernel install --user --name exposome --display-name "Python 3.12 (exposome)"
```

## Project Structure & Execution

- **Run everything from repo root** — notebooks and scripts use relative paths (`data/processed/`, `figures/`, `maps/`, `cache/`).
- `cache/`, `tmp/`, `.conda/` are gitignored. Do not commit them.
- `notebooks/` = monolithic, copy-pasted boilerplate across 6 notebooks. Kept as reference; the active compute layer is moving to `src/exposome/` + `scripts/run_<layer>.py`.
- `scripts/build_master_exposome.py` = merges all processed layers into `data/processed/santiago_exposome_master.{csv,geojson}`.

### Notebook Execution Order

```
1. notebooks/santiago_healthcare_access.ipynb   # or: python scripts/run_healthcare.py
2. notebooks/santiago_air_quality.ipynb
3. notebooks/santiago_green_spaces.ipynb
4. notebooks/santiago_socioeconomic.ipynb
5. notebooks/santiago_climate_heat_exposure.ipynb
6. notebooks/santiago_greenspace_cv.ipynb   # optional
7. python scripts/build_master_exposome.py
```

## Hardcoded Santiago Assumptions

- Region query: `"Región Metropolitana de Santiago, Chile"`
- Admin level: `8` (comunas)
- Expected units: **52 communes** (validated strictly in master builder)
- CRS metric: `EPSG:32719` (UTM 19S — Chile-specific)
- CRS geographic: `EPSG:4326`
- Legacy notebook outputs contain `rm_santiago`; new config-driven layers use `<city>_<layer>{_<suffix>}.{csv,geojson}`.

**Any generalization to other cities must modify these.** The master builder will throw if the row count ≠ 52 or if any `name` duplicates or missing values exist.

## Google Earth Engine

- Project ID: `exposome-api`
- Initialized with: `ee.Initialize(project='exposome-api')`
- `earthengine-api` and `geemap` are installed via pip inside the `exposome` env.
- GEE is **required** for `scripts/run_air_quality.py` (Plan A+ satellite pipeline with ERA5 BLH conversion).
- If GEE auth fails, run `earthengine authenticate` inside the activated env.

## Data Flow

### Legacy (notebooks)
```
APIs (Open-Meteo, OSM, GitHub raw CSVs)
    → notebooks (one per exposome layer)
    → data/processed/*_exposome_rm_santiago.{csv,geojson}
    → scripts/build_master_exposome.py
    → data/processed/santiago_exposome_master.{csv,geojson,json}
```

### New — config-driven pipeline
```
config/cities/<city>.yaml
    → src/exposome/config.py
    → src/exposome/boundaries.py  (reuse existing GeoJSONs)
    → src/exposome/air_quality.py  (GEE satellite)
    → scripts/run_air_quality.py
    → data/processed/<city>_air_quality_satellite_YYYY.{csv,geojson}
```

Healthcare access follows the same pattern, but combines OpenStreetMap with the
official MINSAL/DEIS facility registry when available:

```
config/cities/<city>.yaml
    → src/exposome/healthcare.py
        → src/exposome/healthcare_official.py  (MINSAL/DEIS)
        → OpenStreetMap amenities via osmnx
        → conflation (official wins within 150 m buffer)
    → scripts/run_healthcare.py
    → data/processed/<city>_healthcare_access.{csv,geojson,json}
```

Run with official data (default):
```bash
python scripts/run_healthcare.py
```

Run with OSM only:
```bash
python scripts/run_healthcare.py --no-official
```

Force re-download of the official DEIS CSV:
```bash
python scripts/run_healthcare.py --refresh-official
```

Compute street-network distances (slower, more realistic):
```bash
python scripts/run_healthcare.py --use-network
```

Generate choropleth maps:
```bash
python scripts/plot_healthcare_maps.py
```

Categories currently emitted:
- `n_hospital` — hospitals
- `n_clinic` — clinics / private clinics
- `n_primary_care` — CESFAM, SAPU, SAR, CGU, CGR, PSR, CECOSF, SUR
- `n_pharmacy` — pharmacies (OSM only; DEIS does not publish pharmacies)
- `n_laboratory` — clinical laboratories
- `n_dental` — dental clinics
- `n_mental_health` — community mental health centres (COSAM)
- `n_total` — all health facilities matched by the OSM tags or present in DEIS

Each DEIS-derived category is also split by administrative sector:
- `n_<category>_public` — public / SNSS / municipal / Servicio de Salud / FFAA
- `n_<category>_private` — private providers

Compare the official and OSM inventories:
```bash
python scripts/compare_healthcare_sources.py
```
This writes `data/processed/healthcare_source_comparison_by_commune.csv` and
`data/processed/healthcare_unmatched_facilities.csv`.

### Demography (Censo 2017)

Population counts by commune are extracted from the INE Censo 2017 manzana
microdata and added as a separate layer:

```bash
python scripts/run_demography.py
```

Outputs `data/processed/<city>_demography.csv` with columns such as
`pop_total`, `pop_male`, `pop_female`, `pop_0_14`, `pop_15_64`, `pop_65_plus`
and the corresponding percentages.

`scripts/build_master_exposome.py` merges demography and computes derived
ratios like `health_inhabitants_per_primary_care`.

## Demo Document

LaTeX source lives in `demo_document/`. Compile with:
```bash
cd demo_document && latexmk -pdf exposome_demo.tex
```

## Current Refactor Direction

The project is moving from monolithic notebooks to a **config-driven pipeline**:
- New code belongs in `src/exposome/` as importable modules.
- City configs go in `config/cities/<city>.yaml`.
- CLI scripts go in `scripts/run_<layer>.py`.
- Preserve existing notebooks as reference; do not delete them.

When adding new modules, prefer `typer` for CLI entrypoints and `pyyaml` for config loading.
