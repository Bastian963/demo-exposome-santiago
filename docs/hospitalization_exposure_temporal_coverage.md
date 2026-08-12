# Auditoría temporal de exposiciones para hospitalizaciones

**Fecha de auditoría:** 2026-07-18  
**Estudio:** `santiago_communes`  
**Alcance:** análisis de datos offline; no master, API ni webapp

## Decisión inmediata

La corrida confirmatoria de hospitalizaciones puede continuar. Sus modelos
bayesianos registrados usan PM2.5 antecedente 2000–2017, por lo que las series
anuales faltantes de exposiciones secundarias no invalidan el estimando
confirmatorio ni justifican modificar su protocolo después de iniciado el
muestreo.

La recopilación de años faltantes ahora tiene un CLI separado y no forma parte
de esa corrida. Véase
[`santiago_annual_exposome_downloads.md`](santiago_annual_exposome_downloads.md).
El CLI sólo descarga/materializa exposiciones; no reconstruye este análisis ni
modifica sus trazas.

La brecha más importante está en calor: el archivo esperado
`data/processed/santiago_climate_heat_by_year.csv` no está materializado. Como
consecuencia, la tabla
`analysis/hospitalizations/annual_exposure_matrix_2015_2020.csv` tiene 520
valores válidos para precipitación, 520 para incendios y cero para
`heat_hot_days_30c`. Esto afecta el panel anual exploratorio de calor, no el
NB–BYM2 confirmatorio.

El nombre `annual_exposure_matrix_2015_2020.csv` refleja la ventana modelada,
aunque su inventario externo puede contener 2015–2024. Es deuda de nomenclatura;
los modelos filtran explícitamente 2015–2019 y la sensibilidad 2015–2020.

## Exposiciones registradas en la inferencia

| Exposición | Producto materializado | Cobertura potencial de la fuente | Decisión |
|---|---|---|---|
| PM2.5 | Medias crónicas 2000–2017 y 2015–2022 | ACAG anual 2000–2022 en la colección configurada | Conservar 2000–2017 como confirmatoria; una serie anual serviría sólo para sensibilidades de ventana. |
| NO2 | Media 2024 | Sentinel-5P desde 2018-06-28 hasta el presente | Prioridad alta para una serie anual secundaria 2019–2024; no interpretar causalmente frente a egresos 2018–2019. |
| NDVI/verde | Compuesto estacional 2024 | Landsat 8 desde 2013; Dynamic World desde 2015 | Prioridad alta para 2015–2024, preservando la misma estación Oct–Mar y QA por año. |
| Calor | Capa canónica 2024; serie anual ausente | ERA5-Land desde 1950; ventana del proyecto 2015–2024 | Primera brecha a completar después de la inferencia actual. |
| Sueño contextual | Compuesto transversal | Mezcla de ALAN, ruido y proxies sin ventana anual homogénea | No fabricar una serie anual hasta separar componentes con soporte temporal real. |
| Ruido | Modelo oficial GSU 2023 | Un único mapa oficial, no una serie anual homogénea | Tratar como corte transversal; no hay años omitidos equivalentes. |
| Social | Snapshot OSM 2026 y covariables contemporáneas | OSM actual no equivale a snapshots históricos comparables | Mantener transversal. |
| Caminabilidad | Snapshot OSM | Sin serie histórica reproducible en el pipeline actual | Mantener transversal. |
| Transporte | Snapshot OSM | Sin serie histórica reproducible en el pipeline actual | Mantener transversal. |
| Entorno alimentario | Snapshot OSM | Sin serie histórica reproducible en el pipeline actual | Mantener transversal. |

## Otras capas con cobertura no utilizada

| Capa | Materializado | Disponible | Prioridad |
|---|---|---|---|
| ALAN | 2024 | VIIRS mensual desde 2014 | Media-alta; puede apoyar una futura serie circadiana. |
| Viento | 2024 | ERA5-Land desde 1950 | Media; útil como modificador de dispersión, no como exposición confirmatoria actual. |
| Precipitación | 2015–2024 | CHIRPS desde 1981 | Baja para el protocolo actual, cuya ventana anual ya está completa. |
| Incendios | 2015–2024 | MODIS MCD64A1 desde 2000-11 | Baja para el protocolo actual; 2015–2020 ya está completo. |
| Metales pesados | RETC 2015–2022 | 2024 publicado; 2023 temporalmente en revisión | Media y fuera de la familia registrada de diez exposiciones. |

## Estado local de calor

- Caches Open-Meteo completos: 2015–2019 y 2024.
- Cache 2020: parcial.
- Caches Open-Meteo faltantes: 2020 completo, 2021–2023.
- Caches comparadores ERA5-Land presentes: 2015–2024.
- Salida anual canónica ancha: ausente.

La serie anual debe usar un único método consistente. El runner registrado usa
la misma grilla Open-Meteo y agregación de valle que la capa canónica 2024; no se
deben mezclar los comparadores ERA5-Land con los años Open-Meteo dentro de una
misma serie sólo porque sus caches ya existan.

El antiguo runner anual de calor Open-Meteo se conserva como referencia del
baseline histórico utilizado por este análisis. El nuevo archivo temporal usa
el proveedor canónico actual de `santiago_communes` (ERA5-Land) y no debe
mezclarse automáticamente con esa matriz ya iniciada.

Para inventariar o descargar todos los exposomas anuales faltantes, el humano
puede ejecutar:

```bash
.venv/bin/python scripts/run_santiago_missing_annual_exposomes.py --status
.venv/bin/python scripts/run_santiago_missing_annual_exposomes.py --resume
```

El segundo comando es recopilación de larga duración, con progreso, cache y
reanudación por exposición–año. Sus salidas quedan aisladas bajo
`temporal_exposomes/`; no se debe cambiar simplemente `year: 2024` ni reutilizar
esos archivos en la inferencia confirmatoria sin un protocolo nuevo.

## Fuentes de cobertura

- [Sentinel-5P OFFL NO2, catálogo oficial de Earth Engine](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_NO2)
- [Landsat Collection 2 en Earth Engine](https://developers.google.com/earth-engine/guides/landsat)
- [Dynamic World V1](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
- [VIIRS DNB mensual VCMSLCFG](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_MONTHLY_V1_VCMSLCFG)
- [ERA5-Land Daily Aggregated](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
- [CHIRPS Daily](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY)
- [MODIS MCD64A1 Burned Area](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD64A1)
- [RETC, emisiones al aire de fuentes puntuales](https://datosretc.mma.gob.cl/en_GB/dataset/emisiones-al-aire-de-fuente-puntuales)

Toda ampliación debe entrar como análisis secundario o exploratorio y actualizar
configuración, protocolo, hashes y familias de multiplicidad antes de
interpretarse. No se añadirá retrospectivamente a la corrida confirmatoria ya
iniciada.
