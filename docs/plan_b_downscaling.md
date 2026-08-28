# Plan B: Downscaling satelital a ~1 km con ML

**Estado:** Documentado, no implementado.  
**Objetivo:** Convertir el proxy satelital (AOD 3 km / NO₂ columna) en estimaciones de PM₂.₅ y NO₂ de superficie a ~1 km de resolución, calibradas con estaciones terrestres SINCA.

---

## Por qué Plan B es necesario

Plan A (satélite puro) mejora la **resolución espacial** de 11 km → ~3 km, pero tiene limitaciones:

1. **AOD no es PM₂.₅.**  AOD mide opacidad atmosférica; la conversión a concentración de superficie requiere calibración local.
2. **NO₂ satelital es columna**, no concentración de superficie.  La relación columna-superficie depende de la altura de la capa de mezcla, que varía hora a hora.
3. **3 km sigue siendo grueso** para epidemiología intra-urbana fina (efecto de avenida, barrio industrial, etc.).

Plan B resuelve esto con **downscaling espacial supervisado**.

---

## Arquitectura propuesta

```
Fuentes de entrada
    ├── Satélite:  MODIS AOD 3 km  +  Sentinel-5P NO₂ 3.5 km  (GEE)
    ├── Ground truth:  SINCA estaciones (PM₂.₅, NO₂, O₃, horario)
    └── Covariables espaciales de alta resolución:
            ├── NDVI / vegetación (Sentinel-2, 10 m)
            ├── Elevación (SRTM 30 m)
            ├── Densidad poblacional (WorldPop, ~100 m)
            ├── Distancia a vías principales (OSM)
            ├── Uso de suelo (ESA WorldCover, 10 m)
            └── Emisiones inventario (MAPS Chile, si disponible)

Preproceso
    ├── Extraer raster satelital anual por comuna (Plan A, ya hecho)
    ├── Construir grilla regular 1 km sobre la RM
    ├── Samplear cada covariable en cada celda 1 km
    └── Asignar valor de estación SINCA más cercana a cada celda (para training)

Modelo
    ├── Random Forest espacial  o  XGBoost
    ├── Target:  PM₂.₅ (µg/m³)  y  NO₂ (µg/m³)  medidos en SINCA
    ├── Features:  AOD, NO₂ columna, NDVI, elevación, densidad poblacional,
    │              dist_vía_principal_m, uso_suelo, mes/estación
    ├── Validación:  Leave-one-station-out (LOSO) espacial
    └── Métrica:  R², RMSE, bias espacial

Salida
    ├── Grilla 1 km × 1 km de PM₂.₅ y NO₂ estimados (media anual)
    ├── Zonal stats por comuna (para integrar al master)
    └── Incertidumbre:  std de predicción del ensemble
```

---

## Fuentes de datos detalladas

| Capa | Producto | Resolución | Acceso |
|------|----------|-----------|--------|
| AOD | MODIS MCD19A2 / VIIRS | 3 km | GEE |
| NO₂ columna | Sentinel-5P TROPOMI | 3.5×7 km | GEE |
| PM₂.₅ / NO₂ superficie | SINCA (MMA Chile) | Punto (estación) | Web scrape / API |
| NDVI | Sentinel-2 MSI | 10 m | GEE / Copernicus |
| Elevación | SRTMGL1 | 30 m | GEE |
| Población | WorldPop 2020 | ~100 m | WorldPop website |
| Vías | OpenStreetMap | Vector | OSMnx |
| Uso de suelo | ESA WorldCover 2021 | 10 m | GEE |

---

## Consideraciones metodológicas

### Conversión AOD → PM₂.₅

La ecuación más usada en literatura de exposoma:

```
PM₂.₅ = β₀ + β₁·AOD + β₂·RH + β₃·BLH + β₄·temp + ε
```

Donde:
- **RH** = humedad relativa (afecta tamaño de partículas y AOD)
- **BLH** = altura de capa de mezcla (boundary layer height)
- **temp** = temperatura

SINCA provee PM₂.₅ horario; entrenamos un modelo por estación o un modelo global con estación como efecto fijo.

### Conversión columna NO₂ → superficie NO₂

Similarmente:

```
NO₂_superficie = β₀ + β₁·NO₂_columna + β₂·BLH + β₃·temp + β₄·radiación + ε
```

La altura de la capa de mezcla es crítica: una columna alta con BLH bajo implica alta concentración superficial.

### Validación espacial

Santiago tiene ~15 estaciones SINCA.  Con tan pocas estaciones, un RF puro puede sobreajustar al espacio muestral.  Estrategias:

1. **LOSO (Leave-One-Station-Out):** entrenar con 14, predecir la 15ª.  Repetir.  Esto da una estimación realista del error espacial.
2. **Spatiotemporal CV:** si se tienen datos diarios, validar dejando fuera días enteros (no solo estaciones).
3. **Modelo aditivo espacial (GAM):** como baseline robusto antes de RF.

---

## Roadmap de implementación

1. **Scrapeo SINCA** — automatizar descarga de series horarias 2019-2024 para todas las estaciones de la RM.
2. **Construcción de grilla 1 km** — en EPSG:32719, recortada a la RM.
3. **Extracción de covariables en GEE** — NDVI, elevación, uso de suelo, BLH (ERA5).
4. **Preproceso tabular** — unir estaciones + satélite + covariables por fecha/estación.
5. **Entrenamiento RF** — scikit-learn / xgboost, con búsqueda de hiperparámetros.
6. **Validación LOSO** — reportar R² y RMSE por estación.
7. **Predicción en grilla 1 km** — aplicar modelo a cada celda, exportar raster.
8. **Zonal stats por comuna** — integrar al pipeline master.

---

## Criterio de éxito

- **R² LOSO > 0.6** para PM₂.₅ (realista para ~15 estaciones en una cuenca compleja)
- **R² LOSO > 0.5** para NO₂
- **Bias espacial < 5 µg/m³** (sin sobre-predicción sistemática en el centro)
- **Mapa 1 km visualmente coherente:** vías principales y zonas industriales visibles como hotspots

---

## Alternativas si SINCA es insuficiente

- **OpenAQ:** agregar estaciones de la red internacional que operan en Santiago (Embajada USA, etc.).
- **Transfer learning:** entrenar modelo en ciudad con más estaciones (Los Ángeles, Ciudad de México) y fine-tuning con SINCA.
- **Ensemble simple:** promediar Plan A (satélite puro) + Plan B (ML downscaling) donde la incertidumbre es baja.

---

## Integración con el pipeline existente

```yaml
# config/cities/santiago.yaml (futuro)
air_quality:
  plan: "B"  # o "A" para fallback rápido
  ml_model_path: "models/santiago_aq_downscaler.pkl"
  covariates:
    - ndvi
    - elevation
    - population_density
    - distance_to_road
```

El CLI `scripts/run_air_quality.py` tendría una flag `--plan {A,B}`.

---

*Documento creado: 2024-06-26*  
*Autor: Pipeline refactor BrainLat Exposome Demo*
