# Nivel socioeconomico comunal de Santiago — metodologia

## Objetivo

Esta capa construye un indicador comunal de posicion socioeconomica para las 52
comunas de la Region Metropolitana de Santiago. Su funcion en el exposoma es
proveer un gradiente interpretable de ventaja/desventaja social para:

- contextualizar exposiciones ambientales;
- estratificar rankings y mapas;
- actuar como covariable en comparadores sanitarios y analisis posteriores.

La unidad geografica es la comuna (`admin_level=8`) y la orientacion final del
indice es:

- `mayor valor = mejor posicion socioeconomica`.

## Archivos y salidas

La capa se genera con:

```bash
python scripts/run_socioeconomic.py
```

Salidas principales:

- `data/processed/socioeconomic_exposome_rm_santiago.csv`
- `data/processed/socioeconomic_exposome_rm_santiago.geojson`
- `data/processed/socioeconomic_exposome_rm_santiago_metadata.json`

La figura diagnostica principal se genera con:

```bash
python scripts/plot_socioeconomic.py
```

Figura:

- `figures/socioeconomic_santiago_4panel.png`

## Fuentes

### Componentes del indice compuesto

1. CASEN 2022 via `bastianolea/pobreza_chile`
   - ingreso per capita del hogar: `ytotcor` -> `ingreso`
   - escolaridad media: `esc` -> `escolaridad`
2. CASEN 2022 pobreza multidimensional via `bastianolea/pobreza_chile`
   - `pobreza_multi_p` -> `pobreza_multi_pct`
3. Estimacion SAE de pobreza por ingresos via `bastianolea/pobreza_chile`
   - `pobreza_p` -> `pobreza_pct`
   - `limite_inferior` -> `pobreza_ci_low`
   - `limite_superior` -> `pobreza_ci_high`
   - `poblacion` -> `poblacion`
4. Censo 2017 INE a nivel manzana
   - materialidad deficitaria de vivienda
   - hacinamiento aproximado como personas por hogar

### Indicadores suplementarios

Estos indicadores se agregan como columnas informativas, pero **no entran** al
indice `nse_index` ni al `nse_index_pca`:

- CEAD delincuencia: `tasa_delitos_violentos`, `tasa_delitos_propiedad`
- PAES 2024: `paes_puntaje_promedio`
- Fonasa 2023: `pct_fonasa_tramo_a_b`
- SINIM 2023: `ipp_per_capita`

Su descarga sigue la convencion del repo de "graceful skip": si fallan, la capa
se puede generar igual mientras las columnas nucleo permanezcan completas.

## Procesamiento

1. Se carga `config/cities/santiago.yaml`, bloque `socioeconomic`.
2. Se descargan o reutilizan desde `cache/` las tablas abiertas necesarias.
3. Se filtra la Region Metropolitana usando `region_code=13` y los CUT de comuna.
4. Se normalizan y consolidan nombres de comuna usando el mapeo del Censo 2017.
5. Se agregan los indicadores de vivienda del Censo 2017 desde manzanas a comuna:
   - `viv_materialidad_deficitaria_pct = (MATREC + MATIRREC) / (MATACEP + MATREC + MATIRREC) * 100`
   - `hacinamiento_phh = PERSONAS / CANT_HOG`
6. Se integran los indicadores suplementarios por `comuna_code`.
7. Se hace el join final con las geometrías comunales canónicas.
8. Se validan 52 filas, nombres unicos y ausencia de faltantes en columnas nucleo.

## Construccion del indice

El indice usa seis componentes:

- `ingreso`
- `escolaridad`
- `pobreza_pct`
- `pobreza_multi_pct`
- `viv_materialidad_deficitaria_pct`
- `hacinamiento_phh`

Orientacion:

- `ingreso`, `escolaridad`: mayor = mejor
- `pobreza_pct`, `pobreza_multi_pct`, `viv_materialidad_deficitaria_pct`, `hacinamiento_phh`: mayor = peor

### `nse_index`

1. Cada componente se orienta para que mayor siempre signifique mejor posicion.
2. Cada variable orientada se estandariza con z-score (`ddof=0`).
3. `nse_index` es la media equiponderada de esos seis z-scores.

### `nse_index_pca`

1. Se usa la misma matriz orientada y estandarizada.
2. Se calcula PCA mediante SVD (`numpy.linalg.svd`).
3. Se toma el primer componente principal.
4. Su signo se ajusta para correlacionar positivamente con `ingreso`.
5. El resultado se re-estandariza a z-score y se reporta como `nse_index_pca`.

### `nse_quintil`

`nse_quintil` se deriva con `pd.qcut(nse_index_pca, 5, labels=[1,2,3,4,5])`,
donde:

- `1` = comunas mas vulnerables
- `5` = comunas de mayor posicion socioeconomica

## Validacion y consistencia interpretativa

Checks minimos esperados en auditoria:

- 52 comunas exactas.
- `name` sin duplicados ni faltantes.
- sin `NaN` en columnas nucleo.
- Spearman muy alto entre `nse_index` y `nse_index_pca`, como chequeo de
  sensibilidad de ponderacion.
- ranking interpretable: comunas del sector oriente y centro alto deben tender
  a quedar arriba, y comunas historicamente mas vulnerables abajo.

La metadata exporta:

- varianza explicada por PC1;
- cargas de PC1;
- correlacion de Spearman entre indice equiponderado y PCA.

Existe un bloque opcional de validacion externa en config para contrastar el
indice contra una fuente oficial independiente. Si no hay archivo configurado,
la validacion se omite sin fallar la capa.

## Reproducibilidad

- Ejecutar siempre desde la raiz del repo.
- Usar `.conda/envs/exposome`.
- La primera corrida requiere acceso de red para poblar `cache/`.
- Corridas posteriores pueden regenerar la capa usando el cache local existente.

Comando de chequeo estructural del repo:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python scripts/audit_exposome_status.py --check
```

## Limitaciones

- Es un indicador ecologico a nivel comuna; no representa exposicion o ingreso
  individual.
- Mezcla anos de fuente distintos: Censo 2017, CASEN 2022, Fonasa 2023, PAES
  2024 y delincuencia mas reciente disponible.
- La pobreza por ingresos comunal proviene de estimacion SAE y debe leerse con
  su incertidumbre asociada (`pobreza_ci_low`, `pobreza_ci_high`).
- Los indicadores suplementarios son utiles para contexto, pero no deben
  reinterpretarse como parte del indice compuesto mientras no se rediseñe la
  metodologia.

## Oportunidades de mejora

- Configurar una validacion externa oficial en `data/raw/` y `config/cities/santiago.yaml`.
- Agregar tests unitarios para la orientacion y robustez del PCA.
- Registrar version o fecha efectiva de cada fuente suplementaria en metadata.
- Si se necesita mayor robustez operativa en entornos restringidos, documentar o
  parametrizar mejor la dependencia de red para la primera corrida.
