# Plan A+: Metodología de conversión satelital a concentraciones de superficie

**Autor:** Pipeline refactor BrainLat Exposome Demo  
**Fecha:** 2024-06-26  
**Estado:** Implementado y operativo en `src/exposome/air_quality.py`

---

## Objetivo

Convertir los **proxies satelitales** de calidad del aire (resolución ~3 km) en estimaciones de **concentración de superficie** con unidades epidemiológicamente interpretables (µg/m³), utilizando principios físicos y datos de reanálisis atmosférico.

Esto permite comparar directamente con las guías de la OMS y con los datos legacy de CAMS (~11 km) que ya están en el exposoma maestro.

---

## Resumen ejecutivo

| Variable satelital | Unidad original | Conversión | Unidad final |
|---|---|---|---|
| **NO₂ Sentinel-5P** | Densidad de columna troposférica [mol/m²] | ÷ altura capa de mezcla (ERA5) | **Concentración superficial [µg/m³]** |
| **AOD MODIS** | Profundidad óptica 470 nm [unitless] | *Requiere calibración SINCA* | *Proxy de carga particulada (sin conversión forzada)* |

---

## 1. NO₂: De columna troposférica a concentración superficial

### 1.1 Concepto físico

Sentinel-5P TROPOMI mide la **cantidad total de NO₂ en la columna troposférica** sobre cada píxel. Esto se expresa como:

```
Columna = ∫₀^∞ C(z) dz      [mol/m²]
```

donde `C(z)` es la concentración a altura `z`.

Para obtener la concentración **cerca del suelo** (la que respiramos y la que miden las estaciones), asumimos que el NO₂ está bien mezclado dentro de la **capa límite atmosférica** (boundary layer, BL):

```
C_superficie ≈ Columna / BLH
```

donde **BLH** = Boundary Layer Height [m], la altura hasta donde el aire de superficie se mezcla verticalmente.

### 1.2 Fórmula completa

```
NO₂ [µg/m³] = NO₂ [mol/m²] × M(NO₂) [g/mol] × 10⁶ [µg/g] / BLH [m]
```

Sustituyendo valores:

```
NO₂ [µg/m³] = NO₂_columna × 46.0055 × 1 000 000 / BLH
```

### 1.3 Fuente de BLH

Usamos **ERA5 Hourly** (`ECMWF/ERA5/HOURLY`), banda `boundary_layer_height`, promediada anualmente.

- **Resolución espacial ERA5:** ~31 km (nativo 0.25°)
- **Resolución temporal:** horaria → promedio anual
- **Periodo:** 2024-01-01 a 2024-12-31

**Limitación:** ERA5 tiene resolución mucho más gruesa que el satélite. Usamos el mismo valor de BLH para toda la RM (~300-400 m), lo que introduce incertidumbre, pero captura la variación estacional promedio correctamente.

**Fallback:** Comunas muy pequeñas (ej. Lo Prado, 6 km²) pueden no intersectar la grilla de ERA5. En ese caso usamos la **media regional** de BLH como imputación.

### 1.4 Validación cruzada implícita

Comparamos el rango de NO₂ satelital convertido con CAMS legacy:

| Fuente | NO₂ mínimo | NO₂ máximo | Unidad |
|---|---|---|---|
| CAMS (Open-Meteo) | ~3 µg/m³ | ~43 µg/m³ | µg/m³ |
| Sentinel-5P + ERA5 | ~2 µg/m³ | ~36 µg/m³ | µg/m³ |

Los rangos son **coherentes**, lo que sugiere que la conversión física no introduce sesgos de magnitud. La diferencia espacial (satélite resuelve mejor el gradiente intra-urbano) es precisamente la mejora buscada.

### 1.5 Supuestos y simplificaciones

1. **Mezcla perfecta en la BL:** En realidad, el NO₂ no está uniformemente distribuido. Cerca de fuentes (avenidas, industria) hay gradientes verticales fuertes.
2. **BLH constante espacialmente:** Usamos BLH regional. En la práctica, la BLH varía entre el centro urbano (más baja, ~200-300 m en invierno) y la cordillera (más alta).
3. **NO₂ estratosférico despreciable:** TROPOMI ya corrige por la componente estratosférica; usamos el producto "troposférico".
4. **Resolución del satélite:** 3.5×7 km es el píxel nativo; el valor comunal es un promedio zonal que suaviza hotspots.

---

## 2. PM₂.₅: De AOD a concentración de superficie

### 2.1 Por qué NO convertimos AOD directamente

AOD (Aerosol Optical Depth) mide la **atenuación de la luz** por partículas en la atmósfera. No mide directamente la masa de PM₂.₅ en la superficie.

La relación AOD → PM₂.₅ depende de:
- **Humedad relativa** (las partículas crecen con la humedad)
- **Altura de la capa de mezcla** (misma lógica que NO₂)
- **Composición química** (polvo, carbono negro, sulfatos, nitratos)
- **Tamaño de partícula** (AOD es más sensible a partículas grandes)

### 2.2 Ecuación general (literatura)

```
PM₂.₅ = β₀ + β₁ · AOD · f(RH) / BLH + ε
```

Donde `f(RH)` es el **factor de crecimiento higroscópico**, que modela cómo el AOD aumenta con la humedad.

### 2.3 Por qué necesitamos SINCA para calibrar

Los coeficientes `β₀`, `β₁` y la forma de `f(RH)` son **específicos de cada región**. En Santiago:
- El invierno tiene inversión térmica que atrapa aerosoles cerca del suelo
- La calefacción a leña genera partículas orgánicas con propiedades ópticas distintas al polvo
- La humedad relativa es baja (~40-60%), por lo que `f(RH)` es menos extremo que en ciudades tropicales

**Sin datos de estaciones SINCA, cualquier conversión AOD→PM₂.₅ sería una extrapolación de otras ciudades (Los Ángeles, Pekín) con composición atmosférica diferente.**

### 2.4 Plan de calibración (cuando se tengan datos SINCA)

1. **Obtener promedios anuales 2024** de PM₂.₅ en cada estación SINCA de la RM.
2. **Samplear AOD y BLH** en la ubicación exacta de cada estación.
3. **Ajustar regresión lineal** (o Random Forest simple):
   ```
   PM₂.₅ = β₀ + β₁·AOD + β₂·BLH + β₃·RH + β₄·temp
   ```
4. **Validar con LOSO** (Leave-One-Station-Out): entrenar con 14 estaciones, predecir la 15ª.
5. **Aplicar modelo** a la grilla satelital completa para obtener `pm25_satellite_ug_m3`.

---

## 3. Pipeline de código

### 3.1 Flujo de datos

```
config/cities/santiago.yaml
    └── src/exposome/config.py

src/exposome/boundaries.py          →  GeoDataFrame 52 comunas
src/exposome/gee.py                 →  GeoDataFrame → EE FeatureCollection

src/exposome/air_quality.py
    ├── fetch_no2()                 →  Sentinel-5P TROPOMI  (mol/m²)
    ├── fetch_blh()                 →  ERA5 Hourly          (m)
    ├── fetch_aod()                 →  MODIS MCD19A2        (unitless)
    └── build_air_quality_layer()
            ├── merge all three
            ├── no2_surface_ug_m3 = no2_mean × 46.0055e6 / blh_mean
            ├── validate 52 rows, no missing
            └── write CSV / GeoJSON / metadata
```

### 3.2 Comando de ejecución

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_air_quality_satellite.py
```

Salidas generadas:
- `data/processed/santiago_air_quality_satellite_2024.csv`
- `data/processed/santiago_air_quality_satellite_2024.geojson`
- `data/processed/santiago_air_quality_satellite_2024_metadata.json`

### 3.3 Integración al exposoma maestro

`scripts/build_master_exposome.py` ahora incluye la capa satelital como columnas adicionales:

```python
{
    "name": "air_quality_satellite",
    "csv": "santiago_air_quality_satellite_2024.csv",
    "columns": ["no2_mean", "blh_mean", "aod_mean", "no2_surface_ug_m3"],
    "rename": {
        "no2_mean": "no2_column_mol_m2",
        "aod_mean": "aod_470",
    },
}
```

La tabla maestra final (`santiago_exposome_master.csv`) contiene **ambas fuentes**:
- `no2_mean` (CAMS, µg/m³, legacy)
- `no2_surface_ug_m3` (satélite + ERA5, µg/m³, Plan A+)
- `aod_470` (MODIS, proxy particulado)

Esto permite comparar, validar y eventualmente reemplazar cuando el downscaling ML (Plan B) esté listo.

El detalle de la capa CAMS/Open-Meteo legacy vive en
`docs/air_quality_legacy_methodology.md`.

---

## 4. Limitaciones y honestidad científica

| Aspecto | Limitación | Mitigación |
|---|---|---|
| BLH a 31 km | No captura variación intra-urbana | Usamos media regional; Plan B usará BLH horaria por celda |
| Mezcla perfecta | NO₂ no es uniforme verticalmente | Documentado como aproximación de primer orden |
| Sin calibración PM₂.₅ | AOD no convertido a µg/m³ | Dejado como proxy; conversión documentada para cuando se tengan datos SINCA |
| Resolución 3 km | Aún grueso para calles/industrias | Plan B downscaling a 1 km con covariables de alta resolución |
| Temporal | Solo media anual 2024 | Futuro: series mensuales/estacionales para capturar invierno vs verano |

---

## 5. Referencias clave

1. **Martin, R. V. (2008).** *Global inventory of nitrogen oxide emissions constrained by space-based observations of NO₂ columns.* Journal of Geophysical Research. — Fundamento de la conversión columna→superficie.
2. **Lamsal et al. (2008).** *Validation of OMI tropospheric NO₂ columns.* — Relación entre column density y surface concentration.
3. **Gupta & Christopher (2009).** *Particulate matter air quality assessment using integrated surface, satellite, and meteorological products.* — Marco AOD→PM₂.₅.
4. **ECMWF ERA5 documentation:** https://confluence.ecmwf.int/display/CKB/ERA5 — Detalles de boundary_layer_height.
5. **TROPOMI NO₂ Product User Manual:** https://sentinels.copernicus.eu/web/sentinel/technical-guides/sentinel-5p/products-algorithms — Unidades y correcciones.

---

## 6. Checklist para extender a Plan B

- [ ] Scrapear/limpiar datos SINCA horarios 2019-2024 (~15 estaciones)
- [ ] Construir grilla 1 km en EPSG:32719
- [ ] Extraer covariables en GEE: NDVI (Sentinel-2), elevación (SRTM), uso de suelo (ESA World Cover), distancia a vías (OSM)
- [ ] Entrenar Random Forest / XGBoost con LOSO validation
- [ ] Predecir PM₂.₅ y NO₂ en grilla 1 km
- [ ] Zonal stats por comuna e integrar al master builder
- [ ] Comparar R², RMSE, bias espacial vs Plan A+

---

## 7. Plan A++: O3, Angstrom Exponent y FineModeFraction (2026)

Beyond NO2 and AOD, three additional satellite indicators were added to
broaden the air-quality exposure dimension of the exposome.

### 7.1 O3 (ozono troposférico, Sentinel-5P TROPOMI)

- **Collection:** `COPERNICUS/S5P/OFFL/L3_O3`
- **Band:** `O3_column_number_density` [mol/m²]
- **Native resolution:** ~7 km
- **O3 limitation: stratospheric column.** S5P O3 is the **total
  column** O3, not just tropospheric. Approximately 90% of the
  column is stratospheric; the tropospheric component is small
  and the column is dominated by stratospheric variability. The
  commune-level signal we observe is therefore **dominated by
  stratospheric O3 transport patterns**, not by local
  photochemistry.
- **v1.0 caveat (deprecated).** Earlier versions applied the same
  column * M / BLH conversion that works for NO2 to estimate
  surface O3 in µg/m³. The resulting values (15718-21785 µg/m³)
  and WHO ratios (261-363) are 5-10x above physically plausible
  surface O3 for Santiago, because the formula implicitly
  assumed the entire column sits inside the boundary layer.
- **v1.1 decision: drop surface O3 columns.** In v1.1 we
  **removed** `o3_surface_ug_m3` and `o3_who_ratio` from the
  CSV/master and the corresponding `who_guidelines.o3_peak_season`
  from the city config. The only O3 column retained is
  `o3_mean` (total column in mol/m²), used for **relative
  ranking only**. For absolute surface O3, consult the SINCA
  ground-station network (https://sinca.mma.gob.cl).
- **Use case:** `o3_mean` is included in the master for ranking;
  for exposure analyses, prefer SINCA station data.

### 7.2 AE (Angstrom Exponent, derivado de MODIS MCD19A2)

- **Collection:** `MODIS/061/MCD19A2_GRANULES`
- **Inputs:** `Optical_Depth_047` and `Optical_Depth_055`
- **Computation:** AE_470-550 = -log(AOD_550 / AOD_470) / log(550 / 470)
- **Why derived instead of using the precomputed `AngstromExp_470-780`
  band:** the precomputed band is often null over land in C61.
  Deriving from the two AOD channels is always populated.
- **Interpretation:**
  - AE > 1.5 = fine aerosols (combustion, traffic, biomass burning,
    black carbon).
  - AE ≈ 1.0-1.5 = mixed aerosol.
  - AE < 1.0 = coarse aerosols (dust, sea salt).
- **Santiago finding:** Annual mean AE is 2.10-2.12 across all
  communes (very fine, traffic-dominated urban aerosol). Spatial
  variation is small because the whole RM is under the same urban
  combustion regime.

### 7.3 FineModeFraction (MODIS MCD19A2)

- **Band:** `FineModeFraction` (0-1)
- **Caveat (known issue):** In the current C61 collection, this band
  is **saturated at 1.0** over land, including Santiago. The
  saturation reflects a known retrieval limitation, not a real
  measurement. The column is reported in the output for
  **compatibility with the C6 API** but should not be used for
  ranking or analysis. We document this in the metadata's
  `coverage_gap` block.

### 7.4 Master integration

The columns added to the master (v1.1, after v1.0's v1.1 O3 drop):

- `ae_470_550_mean`, `fine_mode_fraction_mean` (BC proxies)
- `o3_mean` (column, kept as ranking indicator)
- `no2_surface_ug_m3` (NO2 surface concentration)
- `no2_who_ratio` → renamed to `no2_who_ratio_satellite` in the
  master to supersede the legacy CAMS-derived value

Total master columns: 252 → 264 (v1.0) → **274 (v1.1)** (+12 in
v1.0: 6 from air_quality_satellite + 6 from wind; -2 in v1.1:
removal of o3_surface_ug_m3 and o3_who_ratio; +12 in v1.1: 12
seasonal wind columns).

### 7.5 v1.1 changes summary

- `o3_surface_ug_m3` and `o3_who_ratio` removed from the
  air_quality_satellite CSV, master, and city config.
- `o3_mean` retained for relative ranking only.
- WHO 2021 O3 peak-season guideline removed from the config
  (no longer used).
- New `test_o3_surface_columns_dropped` regression test in
  `tests/test_air_quality_satellite.py` ensures these columns
  do not silently reappear.

---

*Documento creado para estudio y revisión metodológica.*
