# Estimaciones de Pobreza Comunal SAE (MDSF, 2017-2024)

Tasas comunales de **pobreza por ingresos** y de **pobreza multidimensional (IPM)** para las 52
comunas de la Región Metropolitana de Santiago, provenientes de las estimaciones oficiales de área
pequeña (SAE) que el Ministerio de Desarrollo Social y Familia (MDSF) publica desde CASEN.

## Fuente

- **Publisher**: División Observatorio Social, MDSF, con asesoría técnica de CEPAL (revisión
  metodológica 2019-2020) y apoyo histórico de PNUD (desde 2009).
- **Landing page**: https://observatorio.ministeriodesarrollosocial.gob.cl/pobreza-comunal
- **Informe metodológico de referencia**: "Estimaciones Comunales de Pobreza por Ingresos en Chile
  Mediante Métodos de Estimación en Áreas Pequeñas", MDSF-CEPAL, dic. 2021. Archivado en
  `data/raw/pobreza_sae/Informe_SAE_2020.pdf`; resumen en `data/raw/pobreza_sae/methodology_notes/informe_sae_2020.md`.
- **Años disponibles**: ingresos 2015/2017/2020/2022/2024; multidimensional 2017/2022/2024.
  **Este proyecto usa 2017/2020/2022/2024 (ingresos) y 2017/2022/2024 (multidimensional) — 2015 se
  excluye del pipeline** (ver Limitaciones).
- **Raw files**: `data/raw/pobreza_sae/` (6 xlsx + 6 PDF + notas metodológicas condensadas en
  `methodology_notes/`, ver ese `README.md`).

## Indicadores

1. **Pobreza por ingresos**: % de personas cuyo ingreso per cápita del hogar está bajo la línea de
   pobreza vigente (metodología actualizada desde CASEN 2013/2015, canasta básica revisada en 2024).
2. **Pobreza multidimensional (IPM)**: % de personas en hogares con carencias en al menos 3 de 5
   dimensiones (Educación, Salud, Trabajo y Seguridad Social, Vivienda y Entorno, Redes y Cohesión
   Social — metodología oficial desde CASEN 2015-2016).

## Método: Small Area Estimation (SAE), Fay-Herriot

CASEN no está diseñada para ser representativa a nivel comunal (335-346 comunas del país no son un
dominio de estudio de la encuesta) — las estimaciones directas comunales serían muy imprecisas. Desde
2009 (ingresos) y 2015 (IPM), el MDSF produce estimaciones SAE: la estimación final por comuna es una
combinación ponderada por varianza entre una **estimación directa** (CASEN, si hay muestra suficiente)
y una **estimación sintética** (regresión sobre covariables administrativas/censales, aplicable a
todas las comunas):

```
θ̂_FH = γ̂ · θ̂_directa + (1 − γ̂) · θ̂_sintética,   γ̂ = σ̂²_u / (σ̂²_u + ψ̂²_d)
```

El peso de la estimación directa crece cuanto menor es su varianza muestral relativa a la varianza
del efecto aleatorio comunal. Una comuna entra al ajuste Fay-Herriot solo si cumple criterios de
calidad (grados de libertad ≥14, muestra ≥50 personas, DEFF ≥1, ≥15 casos de pobreza en la muestra);
si no los cumple o no tiene muestra CASEN, recibe solo la estimación sintética (columna
`*_sae_type_<año>` = `"sintetica"` en los datos procesados). Ver detalle completo en
`data/raw/pobreza_sae/methodology_notes/informe_sae_2020.md`.

Cada vintage (2017, 2020, 2022, 2024) reajusta el set de covariables y el modelo sintético con un
algoritmo de selección propio (en 2024: exclusión por correlación >0,90, depuración VIF, stepwise
BIC sobre 150 iteraciones). Detalle por año en `data/raw/pobreza_sae/methodology_notes/*.md`.

## ⚠️ Comparabilidad entre años — limitada

El propio MDSF advierte explícitamente:

> "para cada versión de las estimaciones SAE se hacen mejoras metodológicas y se ajusta el mejor
> modelo posible para la estimación sintética, dado esto, **las estimaciones SAE no son comparables
> entre distintos años**." (Estimaciones SAE 2024, MDSF)

Además, **2024 incorpora una canasta básica actualizada** — el salto de nivel entre 2022 y 2024 (ej.
La Pintana: pobreza por ingresos 9,29% → 23,30%) refleja en gran parte un cambio de línea de medición,
no necesariamente un empeoramiento real equivalente de las condiciones de vida. Por esto:

- Las columnas `pobreza_ing_change_2017_2022` y `pobreza_multi_change_2017_2024` se calculan **solo**
  sobre tramos internamente comparables (mismo tipo de revisión metodológica), nunca cruzando el
  quiebre de canasta 2024 para ingresos.
- En el webapp, la serie de años se presenta en **sub-pestañas** (no slider animado de tendencia), para
  evitar sugerir una evolución continua que la metodología no respalda.
- 2015 se excluyó del todo: usa la línea de pobreza pre-revisión de dic. 2014/ene. 2015 y el informe
  fuente no publica una tabla de resultados numéricos parseable (solo mapas), ver
  `data/raw/pobreza_sae/methodology_notes/resultados_pobreza_comunal_2015.md`.

## Corrección de un error de datos preexistente en la capa `socioeconomic`

Antes de esta incorporación, la capa `socioeconomic` (`src/exposome/socioeconomic.py`) obtenía
`pobreza_pct` desde `bastianolea/pobreza_chile/pobreza_comunal.csv` (fuente de terceros, no oficial
directa). Se verificó que **ese CSV entrega valores de pobreza multidimensional 2022, etiquetados
como pobreza por ingresos**: para La Pintana, el proyecto reportaba `pobreza_pct = 27.0`, que coincide
exactamente con el IPM oficial 2022 (27.00%), mientras que la pobreza por ingresos oficial 2022 de
La Pintana es 9.29%. Esto hacía que el `nse_index` contara dos veces la pobreza multidimensional (una
vez como `pobreza_pct` mal etiquetado, otra como `pobreza_multi_pct`).

Con la incorporación de esta capa, `socioeconomic.py` se repuntó para leer `pobreza_pct`,
`pobreza_ci_low/high` y `poblacion` desde `pobreza_sae.read_income_year(raw_dir, 2022)`, y
`pobreza_multi_pct` desde `pobreza_sae.read_multi_year(raw_dir, 2022)` — ambos desde las planillas
oficiales MDSF archivadas en `data/raw/pobreza_sae/`. Los nombres de columna en `socioeconomic` no
cambiaron (para no romper consumidores downstream), pero sus valores sí — ver
`CHANGELOG.md` para el detalle de outputs regenerados.

## Output columns

`data/processed/santiago_pobreza_sae.csv` (52 filas):

- **`name`** — nombre de comuna (canónico, mismo join key que el resto de las capas).
- **`pobreza_ing_2017` / `_2020` / `_2022` / `_2024`** — % pobreza por ingresos, estimación SAE.
- **`pobreza_ing_ci_low_<año>` / `_ci_high_<año>`** — intervalo de confianza 95% (%).
- **`pobreza_ing_sae_type_<año>`** — `"directa_sintetica"` (Fay-Herriot) o `"sintetica"`.
- **`pobreza_multi_2017` / `_2022` / `_2024`** — % pobreza multidimensional (IPM), estimación SAE.
- **`pobreza_multi_ci_low_<año>` / `_ci_high_<año>` / `_sae_type_<año>`** — análogos.
- **`pobreza_ing_change_2017_2022`** — puntos porcentuales, tramo comparable (excluye 2024).
- **`pobreza_multi_change_2017_2024`** — puntos porcentuales (IPM sin quiebre de canasta).

Columna principal para webapp/master: `pobreza_ing_2024` (ingresos) y `pobreza_multi_2024` (IPM),
año más reciente de cada indicador.

## Limitaciones

1. **No comparable entre años** de forma estricta (ver arriba) — usar como nivel por año, no como
   serie de tendencia continua.
2. **2015 excluido** del pipeline por línea de pobreza distinta y falta de tabla numérica parseable.
3. **Estimación sintética en algunas comunas** cada año (columna `*_sae_type_<año>`), con mayor
   incertidumbre al no incorporar dato directo de CASEN para esa comuna.
4. **Resolución solo comunal** — no hay desagregación sub-comunal (`resolution: comuna`,
   `has_fine_layer: false`).
5. **Cambio de canasta básica 2024** afecta directamente el nivel de la serie de ingresos, no solo su
   precisión.

## Reproducibilidad

- Inputs versionados en el repo (`data/raw/pobreza_sae/`), sin API key ni acceso a red para reproducir.
- Pipeline: `python scripts/run_pobreza_sae.py` (`src/exposome/pobreza_sae.py`).
- Semillas aleatorias: ninguna (lectura determinística de las planillas oficiales publicadas).
