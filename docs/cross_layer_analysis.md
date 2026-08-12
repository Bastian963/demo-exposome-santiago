# Cross-layer analysis (EBI + spatial autocorrelation + clustering + double-burden + PCA)

The master exposome table holds 272 indicators across 25 thematic
layers for the 52 communes of the Region Metropolitana de Santiago.
Each layer is meaningful on its own, but the **brain-health
question** is rarely "what is the PM2.5 of commune X" — it is
"which communes carry a **combination** of multiple environmental
burdens, and how does that combination relate to the
socioeconomic gradient?"

This document describes the v1.2 cross-layer analysis shipped in
`scripts/analyze_cross_layer.py` and the supporting scripts
`scripts/spatial_autocorrelation.py` and
`scripts/cluster_communes.py`.

## Outputs (and where they live)

### Headline cross-layer artefacts (v1.2)

| Artefact | Path | Rows x Cols | Script |
|---|---|---|---|
| EBI per commune | `data/processed/environmental_burden_index.csv` | 52 x 28 | `analyze_cross_layer.py` |
| Cross-layer summary | `data/processed/cross_layer_summary.json` | (json) | `analyze_cross_layer.py` |
| Spatial autocorrelation | `data/processed/spatial_autocorrelation.json` | (json) | `spatial_autocorrelation.py` |
| Commune clusters | `data/processed/commune_clusters.csv` | 52 x 4 | `cluster_communes.py` |
| Time-series trends | `data/processed/time_series_trends.csv` | 208 x N | `time_series_trends.py` |

### Figures

| Artefact | Path | Description |
|---|---|---|
| Correlation matrix | `figures/correlation_matrix_cross_layer.png` | 20x20 heatmap |
| Hotspot scatter (4 panels) | `figures/socio_environmental_hotspots.png` | EBI vs NSE, PM2.5, etc. |
| EBI choropleth | `figures/environmental_burden_index.png` | single panel |
| EBI-PCA loadings | `figures/ebi_pca_loadings.png` | 6 PCs heatmap |
| Effective dose map | `figures/effective_dose_winter_map.png` | choropleth + scatter |
| Spatial autocorrelation (LISA) | `figures/spatial_autocorrelation_lisa.png` | 4-panel |
| Spatial autocorrelation (bar) | `figures/spatial_autocorrelation_bar.png` | Moran's I bar |
| Commune clusters map | `figures/commune_clusters_map.png` | k=4 clusters |
| Time-series trends | `figures/time_series_trends.png` | 4-panel slopes |

The EBI does **not** enter the master CSV; the master remains a
pure ingestion table. EBI, clusters, spatial I and trends are
**derived** artefacts that can be regenerated from the master at
any time.

## Pipeline

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/build_master_exposome.py
python scripts/analyze_cross_layer.py
python scripts/spatial_autocorrelation.py
python scripts/cluster_communes.py
python scripts/time_series_trends.py
```

## Canonical indicator set (20 indicators)

The cross-layer analysis collapses each thematic layer to **one
headline indicator** (or two where the layer carries both a
"coverage" and a "burden" component). Each indicator is assigned
a sign: `+1` = higher value means higher burden, `-1` = higher
value means lower burden. This sign convention lets the EBI
average rank-percentiles without further flipping.

| Layer | Indicator | Column | Sign |
|---|---|---|---|
| Air | PM2.5 (ACAG) | `pm25_mean` | +1 |
| Air | NO2 surface (sat) | `no2_surface_ug_m3` | +1 |
| Air | O3 column (sat) | `o3_mean` | +1 |
| Air | AOD 470 nm | `aod_470` | +1 |
| Toxics | Heavy metals index | `hm_index` | +1 |
| Light | ALAN radiance | `alan_radiance_mean` | +1 |
| Sound | Noise combined % | `noise_combined_pct` | +1 |
| Heat | Heat exposure | `heat_exposure_index` | +1 |
| Heat | Urban heat anomaly | `urban_heat_anomaly_c` | +1 |
| Climate | Wildfire burned pct | `fire_burned_pct_mean_annual` | +1 |
| Climate | Wind calm annual | `wind_calm_pct` | +1 |
| Green | Greenspace NDVI | `green_cover_pct_ndvi` | -1 |
| Green | Green area km2 | `green_km2` | -1 |
| Walk | Walkability index | `walk_index` | -1 |
| Transit | Transit index | `transit_index` | -1 |
| Health | Primary care density | `health_n_primary_care` | -1 |
| Food | Food swamp ratio | `food_swamp_ratio` | +1 |
| Socio | Pobreza % | `pobreza_pct` | +1 |
| Socio | NSE index | `nse_index` | -1 |
| Socio | Hacinamiento | `hacinamiento_phh` | +1 |

## Environmental Burden Index (EBI)

For each indicator we convert to a **rank-percentile** in [0, 1],
flipping the sign so that higher = more burden. The EBI for a
commune is the **mean** of the available rank-percentiles (NaNs
are skipped per row, not per indicator). EBI is in [0, 1]; higher
= more cumulative environmental burden.

```text
ebi_score(c) = mean over i in canonical: rank_pct(col_i(c)) * sign_i
ebi_rank(c)  = average rank among 52 communes (1 = highest burden)
```

### Top 5 / Bottom 5 by EBI (v1.2 master)

**Top 5 (highest burden):**

| Rank | Commune | EBI score | Profile |
|---|---|---|---|
| 1 | Lo Espejo | 0.692 | industrial periphery, high PM2.5 + noise + low greenspace |
| 2 | Cerrillos | 0.663 | industrial cordón, high NO2 + heavy metals |
| 3 | Tiltil | 0.597 | semi-rural north, high wildfire + low healthcare |
| 4 | Estación Central | 0.594 | central commuter hub, ALAN + NO2 + transit stress |
| 5 | Pedro Aguirre Cerda | 0.588 | dense low-NSE, industrial noise |

**Bottom 5 (lowest burden):**

| Rank | Commune | EBI score | Profile |
|---|---|---|---|
| 52 | Las Condes | 0.328 | high-NSE, mature tree cover, walkable |
| 51 | La Florida | 0.350 | Andean foothill greenspace, middle-NSE |
| 50 | La Reina | 0.359 | residential-Andes, low industry |
| 49 | Peñalolén | 0.373 | Andean foothill, low PM2.5 |
| 48 | Providencia | 0.400 | dense but very high NSE, tree cover |

### Hotspots (high burden + high deprivation)

Hotspots are defined as communes with `ebi_score > p75` AND
`nse_quintil >= 4` (i.e., higher deprivation). For the v1.2
master the only hotspot is:

- **Independencia** (EBI rank 5, NSE quintil 4)

Independencia is the commune where environmental burden is
**concentrated in already-vulnerable populations** — the most
policy-relevant signal in the cross-layer analysis. Quilicura
(EBI rank 12, NSE quintil 4) is the second candidate.

## EBI-PCA (v1.2 alternative view)

To address the **multicollinearity** of the canonical EBI (rho >
0.9 between ALAN/Transit/Walkability and between Heat exposure /
Urban heat anomaly), we compute a **PCA-weighted EBI** as an
alternative view:

- Standardise the 20 canonical indicators (z-score).
- Apply PCA with Kaiser criterion (eigenvalue > 1).
- For each commune, weight the canonical rank-percentiles by the
  absolute value of PC1's loadings, and rank-percentile the result.
- This yields `ebi_pca_score` and `ebi_pca_rank`.

For v1.2, **6 components** are retained, capturing **86.7%** of
total variance.

### Top 5 / Bottom 5 by EBI-PCA

**Top 5 (highest burden per PCA):**

| Rank | Commune | EBI-PCA score |
|---|---|---|
| 1 | Providencia | 1.000 |
| 2 | Santiago | 0.981 |
| 3 | Ñuñoa | 0.962 |
| 4 | Macul | 0.942 |
| 5 | San Miguel | 0.923 |

**Bottom 5 (lowest burden per PCA):**

| Rank | Commune | EBI-PCA score |
|---|---|---|
| 52 | Alhué | 0.019 |
| 51 | San Pedro | 0.038 |
| 50 | Tiltil | 0.058 |
| 49 | Curacaví | 0.077 |
| 48 | San José de Maipo | 0.096 |

The EBI-PCA top 5 are the **dense urban core** (communes with
high ALAN, NO2, walkability, transit, heat — all positively
loaded on PC1). The bottom 5 are **rural periphery** (low density
across all axes). Note that EBI-PCA and the rank-percentile EBI
rank the **same communes in different positions**: the rank EBI
weights rural industrial hotspots (Lo Espejo, Cerrillos) higher
than the urban core, while PCA-weights the urban core higher.
The two views are **complementary**, not contradictory.

## Double-burden index (v1.2)

A complementary score that combines **environmental burden** (EBI)
with **socioeconomic deprivation** (1 − normalised NSE):

```text
db_score(c) = 0.5 * ebi_score(c) + 0.5 * (1 - rank_pct(nse_index(c)))
```

This explicitly identifies communes where **environmental AND
socioeconomic burdens co-occur**, which is the classic
environmental-justice signal. The top 10 by double-burden for v1.2:

1. Alhué
2. Calera de Tango
3. Cerrillos
4. Cerro Navia
5. Lampa
6. Lo Espejo
7. Paine
8. Tiltil

The list mixes **industrial peri-urban** (Cerrillos, Cerro Navia,
Lo Espejo) with **rural low-NSE** (Alhué, Calera de Tango, Paine,
Tiltil, Lampa) — both ends of the deprivation spectrum.

## Effective dose (v1.2)

`effective_dose_mean` is the **mean of per-pollutant winter-dose
scores**, where each pollutant is

```text
effective_dose_pollutant(c) = rank_pct(pollutant(c)) * wind_calm_pct_winter(c)
```

for PM2.5, NO2, and O3. The intuition: high pollution is worse
when wind doesn't disperse it. Winter calm is used because cold
season has the highest pollutant concentration episodes
(heating, low BLH). Spearman correlation with PM2.5 is high
(rho > 0.5 in v1.2), confirming the construct.

Top 5 effective dose: typically the same communes as EBI top 5
(Lo Espejo, Cerrillos, Estación Central), reflecting that
high-pollution communes also have low winter wind.

## Spatial autocorrelation (v1.2)

`scripts/spatial_autocorrelation.py` computes **Global Moran's I**
and **LISA (Local Moran)** for the 14 most relevant layers,
using **Queen contiguity weights** (row-standardized) and **999
permutations** for inference. The master GeoJSON defines the
neighbour structure (52 polygons).

### Global Moran's I (top 6 layers)

| Rank | Layer | I | z-score | p | Interpretation |
|---|---|---|---|---|---|
| 1 | NO2 surface (sat) | 0.766 | 9.74 | 0.001 | strong positive |
| 2 | ALAN radiance | 0.703 | 9.28 | 0.001 | strong positive |
| 3 | Transit | 0.690 | 8.57 | 0.001 | strong positive |
| 4 | Greenspace NDVI | 0.688 | 8.46 | 0.001 | strong positive |
| 5 | Walkability | 0.634 | 8.49 | 0.001 | strong positive |
| 6 | PM2.5 (ACAG) | 0.626 | 8.37 | 0.001 | strong positive |

All 14 layers have **positive, significant** spatial
autocorrelation except **heavy metals** (I = -0.017, p = 0.124,
spatial randomness) — RETC industrial emissions are
point-source-driven, not spatially clustered at commune level.

### LISA cluster counts (HH = high-high, LL = low-low)

The **LISA quadrant counts** reveal where the burden is
concentrated:

- **NO2**: 13 HH (industrial core: Quilicura, Conchalí, Renca,
  etc.) + 15 LL (rural periphery).
- **ALAN**: 14 HH (urban core) + 16 LL (rural).
- **PM2.5**: 14 HH (central-south, low-NSE) + 5 LL (Andes
  foothills).
- **Greenspace NDVI**: 13 HH (rural/foothill) + 13 LL (urban).
- **Heavy metals**: 0 HH, 2 LL, 2 HL — no spatial clustering.

The HH/LL symmetry is the **fundamental spatial structure** of
the Santiago exposome: a clear urban core vs. rural periphery
gradient, with industrial pollution concentrated in the inner
ring.

## Commune clusters (v1.2)

`scripts/cluster_communes.py` runs **K-means** (k=4) over 6
canonical features: PM2.5, NSE, NDVI, walkability, urban heat
anomaly, primary care density. K is selected by **silhouette**
over k in [3, 5]. v1.2 picks k=4 (silhouette = 0.407, the
maximum in the search range).

| Cluster | Label | Size | Description |
|---|---|---|---|
| 0 | rural-verde | 21 | Rural communes with high greenspace, low PM2.5, low NSE. |
| 1 | industrial-periferia | 21 | Dense industrial core, high PM2.5 + heavy metals, low NSE. |
| 2 | periurbana-mixta | 5 | Mid-density peri-urban (La Florida, Maipú, Pudahuel, Puente Alto, San Bernardo). |
| 3 | residencial-Andes | 5 | High-NSE, tree-covered Andean foothills (La Reina, Las Condes, Providencia, Vitacura, Ñuñoa). |

The cluster labels are derived from **rank-based rules** (not
median), ensuring the labelling is stable across the master.
The four clusters reproduce the spatial structure: rural
periphery (cluster 0), industrial core (cluster 1), peri-urban
transition (cluster 2), and high-NSE residential Andes (cluster
3).

## Time-series trends (v1.2)

`scripts/time_series_trends.py` runs **Mann-Kendall** (with tie
correction) and **Sen's slope** on 4 variables × 52 communes
(208 rows total):

- `tmax` (annual max temperature, ERA5-Land)
- `hot_days_30c` (annual count of days with Tmax > 30 °C)
- `precip` (annual total precipitation, CHIRPS)
- `fire_detections` (annual FIRMS active-fire count)

For v1.2 the median slope of tmax is **-0.07 °C/yr** (artefact of
the 2015-2021 mega-drought, not significant), and a small set
of communes (typically Lampa, Tiltil, Alhué) show **significantly
increasing** fire detections (Mann-Kendall p < 0.05). The trends
are stored in `data/processed/time_series_trends.csv` (208 rows)
and summarised in `data/processed/time_series_trends_summary.json`.

## Strong correlations (|rho| > 0.5)

The Spearman correlation matrix highlights 41 pairs with
|rho| >= 0.5 in the v1.2 master. The top-5 strongest:

| Indicator A | Indicator B | rho |
|---|---|---|
| Heat exposure | Urban heat anomaly (C) | +0.96 |
| ALAN radiance | Transit index | +0.953 |
| Walkability index | Transit index | +0.94 |
| ALAN radiance | Walkability index | +0.938 |
| NO2 surface (sat) | ALAN radiance | +0.928 |

The first row reflects **multicollinearity** in the heat pillar
(both columns measure the same underlying urban heat signal);
this is documented in the cross-layer summary JSON and the EBI
**double-counts the heat pillar** by construction. The next
three rows reflect the structural **urban-core gradient**:
central, well-walkable, transit-rich communes are also the
most light-polluted and NO2-burdened.

## Limitations

1. **Equal weighting.** The rank-percentile EBI uses mean of
   rank-percentiles; each pillar contributes equally. PCA-weighted
   (EBI-PCA) and double-burden variants are provided as
   alternatives but require domain input for stakeholder
   weighting.
2. **Multicollinearity.** Several canonical indicators are
   highly correlated (rho > 0.9). EBI double-counts them
   silently. EBI-PCA de-correlates but is harder to interpret.
3. **Static cross-section.** EBI is computed from the 2024
   snapshot. Time-series trends are reported separately
   (Mann-Kendall + Sen) but the EBI itself is cross-sectional.
4. **No causality.** Cross-layer analysis is descriptive.
   "Hotspots" identifies **co-location** of burden and
   deprivation; it does **not** establish that one causes the
   other.
5. **N = 52.** Commune-level aggregation gives a small
   sample for correlation tests. Spearman with 52 observations
   has reasonable power for rho > 0.4 but cannot reliably
   detect weak correlations (rho < 0.3).
6. **Climate dedup.** OM and ERA5-Land climate metrics are
   **complementary** (max rho = 0.80 < 0.95); they are not
   de-duplicated.
7. **The master is a single-city snapshot.** Generalisation
   to other cities is out of scope for v1.2; multi-city
   cross-layer would require normalisation by city-level
   distribution. The master builder is already unit-agnostic
   (v1.3) and ready for zip-code-level extension.

## What the cross-layer analysis is NOT

- It is **not a causal model**. EBI does not claim that
  "high EBI causes high deprivation" or vice versa.
- It is **not a regression-based exposure index** (e.g., the
  Air Pollution Index from US-EPA). It is purely
  rank-percentile-based and not interpretable in physical
  units.
- It is **not an intervention target list.** A high EBI
  commune is a candidate for further investigation, not a
  prescription.

## Reproducibility

- Source: `data/processed/santiago_exposome_master.csv`
  (52 rows x 272 cols, generated by
  `scripts/build_master_exposome.py`).
- Indicators: hard-coded in
  `scripts/analyze_cross_layer.py:CANONICAL_INDICATORS`.
- Random seeds: K-means uses `random_state=42`; permutation
  tests use 999 permutations. Both deterministic.
- Re-run: `python scripts/analyze_cross_layer.py` and the
  three companion scripts.
- Pre-processed outputs: byte-deterministic given the same
  master.
