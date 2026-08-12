# Metodología — Comparación de distribuciones entre ciudades (panel ANALYTICS)

## Propósito

El panel ANALYTICS del webapp (accesible solo desde la vista LATAM, el único
contexto donde coexiste más de una ciudad) compara la **distribución** de
cada indicador del exposoma entre las ciudades publicadas: histograma de
densidad superpuesto y distribución acumulada empírica (eCDF) superpuesta,
con dos pruebas de hipótesis (Kolmogorov-Smirnov y Anderson-Darling
k-muestral) para cuantificar la diferencia entre ciudades.

Motivación: algunas ciudades incluyen zonas periurbanas o rurales dentro de
su AOI de estudio, y no queríamos ni (a) recortar esos valores para
"limpiar" la comparación, ni (b) dejar que un puñado de valores extremos
domine la escala visual. La solución adoptada es mostrar **todo** el dato
dentro del AOI de cada estudio, usando estadística robusta (mediana + MAD)
que no se ve arrastrada por la cola, y anotando explícitamente cuántos
valores caen fuera del rango visible en vez de descartarlos en silencio.

## Arquitectura: todo el cómputo en Python, el webapp solo dibuja

Todo el cómputo estadístico (escala robusta, bins del histograma, puntos de
la eCDF, KS, Anderson-Darling) se hace en `src/exposome/distributions.py` y
se materializa en un solo artefacto JSON:

```
scripts/export_webapp_distributions.py
  → webapp/public/data/v1/analytics/distributions.json
      → webapp/src/panels/analytics-compare.js (solo renderiza)
```

El webapp **nunca** recalcula un p-value client-side. La razón concreta: la
estandarización del estadístico de Anderson-Darling k-muestral (Scholz &
Stephens 1987) con corrección por empates, y la interpolación de su tabla de
significancia, son fáciles de implementar mal; `scipy.stats.anderson_ksamp`
ya lo hace correctamente y además acota el p-value de forma honesta
(~[0.001, 0.25]) en vez de subdesbordar a `p≈1e-300` como haría un cálculo
ingenuo con miles de píxeles.

Para regenerar el artefacto tras publicar un nuevo estudio o cambiar un
layer:

```bash
python scripts/export_webapp_distributions.py --dry-run   # resumen sin escribir
python scripts/export_webapp_distributions.py             # escribe el JSON
```

Es un script local y rápido (lee `master.csv` ya publicados y rásters
nativos ya materializados; no llama a GEE/Open-Meteo/OSM/Esri), por lo que
no cae bajo la política de "nunca ejecutar scripts de recolección de
datos" — se ejecuta directo, igual que `analyze_cross_layer.py` o los
`export_webapp_*.py` existentes.

## Las dos muestras: fina vs administrativa

Cada indicador se compara sobre **una** de dos muestras posibles, nunca
mezcladas:

- **Grilla fina** (`sample_level: "fine"`): valores por píxel del COG
  publicado (o del `subcomuna/*.geojson` para verde), miles de puntos por
  ciudad. Sólo se usa cuando al menos dos ciudades publican el detalle y el
  manifest v3 certifica que conserva la resolución canónica.
- **Unidad administrativa** (`sample_level: "admin"`): una fila por comuna/
  unidad en `master.csv`, ~50-55 puntos por ciudad. Cubre las ~180 columnas
  numéricas compartidas por al menos 2 estudios (columnas presentes en una
  sola ciudad se excluyen del índice: no hay nada que comparar).

**Nunca se combinan los dos niveles del mismo físico**: el `no2` fino es
columna troposférica en mol/m² (producto satelital S5P), mientras que
`no2_surface_ug_m3` (admin) es un proxy de superficie en µg/m³ — son
cantidades físicas distintas y compararlas directamente sería un error de
unidades, no una comparación válida. Lo mismo aplica al viento: el raster
fino tiene 3 bandas (u, v, velocidad); el exportador usa únicamente la banda
de velocidad declarada por el descriptor `detail.band` del manifest publicado
para que sea comparable al escalar `wind_speed_mean` de nivel admin.

## Escala robusta: mediana ± 3·σ̂ asimétrico (doble-MAD)

La mayoría de los indicadores del exposoma son fuertemente asimétricos a la
derecha (p. ej. luminosidad nocturna ALAN: de ~0.7 a ~89 en la misma
ciudad). Una banda **simétrica** mediana ± 3·(1.4826·MAD) sobre datos así:

- Pone el borde inferior por debajo de cero — sin sentido físico para una
  concentración o una radiancia.
- No captura la cola derecha real (el borde superior queda subestimado).

Por eso se usa el **doble-MAD asimétrico** (Rosenmai 2013): el MAD se calcula
por separado sobre los valores `≤ mediana` y sobre los `≥ mediana`,
produciendo `σ̂↓` y `σ̂↑` independientes. La banda final es
`[mediana − 3·σ̂↓, mediana + 3·σ̂↑]`, recortada al piso físico (0) cuando
**todos** los valores observados en **todas** las ciudades del indicador son
≥ 0 (heurística basada en el dato mismo, no en una lista curada de signos por
columna — así no se desactualiza si cambia el indicador).

La constante `1.4826 = 1/Φ⁻¹(0.75)` es el factor de consistencia estándar que
hace que el MAD estime la misma escala que la desviación estándar bajo
normalidad (Leys, Ley, Klein, Bernard & Licata, 2013, *Journal of
Experimental Social Psychology*: "Detecting outliers: Do not use standard
deviation around the mean, use absolute deviation around the median").

**Cuándo la escala queda indefinida**: si más de la mitad de los valores de
un lado son idénticos a la mediana (común en indicadores con exceso de ceros
o de valores repetidos — conteos de incendios, columnas de bandera booleana),
el MAD de ese lado es 0. El exportador cae primero a un estimador basado en
IQR (`IQR/1.349`); si el IQR **también** es 0 (columna prácticamente
constante en ambas ciudades), esa mitad de la banda se marca
`scale_undefined` y el panel omite dibujarla en vez de colapsarla a una línea
sin ancho. El histograma se sigue dibujando igual.

## Histograma: densidad compartida, con "desborde" en vez de recorte

Los bins son compartidos entre ciudades (mismo ancho, mismo rango) para que
las barras sean comparables. El número de bins usa Freedman-Diaconis sobre la
muestra agrupada, acotado a un máximo (60 por defecto) — sin el tope, un
indicador con 78 000 píxeles (ALAN) generaría miles de bins.

El rango visible del eje X es el percentil agrupado [0.5, 99.5] ampliado para
cubrir la banda doble-MAD de cada ciudad (para que la banda nunca quede
cortada fuera de vista). Los valores fuera de ese rango **no se descartan del
cómputo**: se cuentan en `overflow_low`/`overflow_high` por ciudad y el panel
los anota en el borde del gráfico (p. ej. "⇤23"), en vez de dejar que un solo
valor extremo aplaste la resolución visual de toda la masa central. Las
barras se dibujan en **densidad** (no en conteos), porque el tamaño de
muestra difiere fuertemente entre el nivel fino (miles) y el admin
(decenas).

## eCDF, Kolmogorov-Smirnov y Anderson-Darling k-muestral

La eCDF de cada ciudad se dibuja completa (nunca se recorta: por
construcción va de 0 a 1 sobre todo el rango de datos), submuestreada a un
máximo de puntos preservando siempre los extremos exactos.

- **KS de 2 muestras** (`scipy.stats.ks_2samp`): `D = supₓ |F̂₁(x) − F̂₂(x)|`,
  acotado en [0, 1] — la brecha máxima entre las dos curvas. El panel marca
  esa brecha con una línea vertical cuando hay exactamente 2 ciudades
  seleccionadas (con más de 2, las brechas por par se multiplican y un solo
  marcador induciría a pensar que hay "una" brecha).
- **Anderson-Darling k-muestral** (Scholz & Stephens, 1987, *JASA* 82:
  918-924, vía `scipy.stats.anderson_ksamp`): generaliza KS a k≥2 ciudades a
  la vez con corrección por empates. El p-value que reporta scipy está
  acotado por su tabla de significancia (~0.1%-25%); el artefacto expone
  `p_capped` y **`p_cap_side`** (`floor`/`ceiling`/`null`), porque los dos
  extremos significan cosas **opuestas**: `floor` (p≤0.001) = distribuciones
  claramente distintas; `ceiling` (p≥0.25) = indistinguibles con este test.
  El panel ramifica en tres según `p_cap_side` — colapsarlos en un solo caso
  "acotado por tabla" imprimiría el veredicto inverso para ciudades parecidas
  (real: 10 de los ~180 indicadores admin caen en el techo).

### El problema del n grande: leer primero el estadístico, no el p-value

Santiago y Buenos Aires son *a priori* ciudades distintas — la hipótesis nula
de "misma distribución" es una hipótesis de paja. Con miles de píxeles
espacialmente autocorrelacionados (grilla fina), casi cualquier par de
ciudades produce un p-value que colapsa a ~0 sin importar cuán grande sea la
diferencia real (Armstrong, 2019, *Ophthalmic and Physiological Optics*:
"Is there a large sample size problem?"). Por eso el panel antepone
**siempre** el estadístico como tamaño de efecto (`D` acotado en [0,1];
`A²`) y muestra el p-value en segundo plano, con una advertencia explícita
(`spatial_autocorrelation`) cuando el indicador es de nivel fino y el tamaño
de muestra supera un umbral (`FINE_SAMPLE_AUTOCORR_WARNING_N` en
`distributions.py`).

## Interfaz v3: el selector es el catálogo de exposomas

El panel es a **pantalla completa** (bajo el header GEMMA, cuya altura se mide
en runtime para posicionarlo) y su selector **es el mismo catálogo de exposomas
que muestra el picker** (`webapp/public/palette.json` → `exposomes`), no una
taxonomía propia. Esto reemplaza tanto el `<select>` de 185 columnas de la v1
como el riel de "familias" inferidas de la v2. El contrato "Python computa, el
webapp dibuja" no cambia.

### El riel = el picker (`exposome_id`, `category`)

El riel se construye desde `getPalette().exposomes` agrupado por las **3
categorías** del picker (`entorno` / `sociedad` / `resultados`), en el mismo
orden y con los mismos sprites (`icon-<id>`), reutilizando el patrón de
`city-overview.js`. Cada tarjeta es un exposoma; los grupos (Calor, Lluvia) se
muestran colapsados y se despliegan a sus hijos (`heat_index`,
`heat_summer_tmax`, …) al hacer clic, igual que en el picker.

La única parte frágil —mapear una columna del `master.csv` al exposoma que el
picker muestra— vive **una sola vez** en `registry_by_column`
(`scripts/export_webapp_distributions.py`): el exporter estampa el
`exposome_id` en cada indicador y el panel **empata el dato por ese id**, nunca
re-derivando una familia por prefijos. Los padres de agrupación (`status:
group`) se saltan en el join, de modo que la columna compartida
(`heat_exposure_index`, `precip_extremes_index`) resuelve al hijo concreto, no
al padre. Esto elimina de raíz las trampas de substring de la v2 (`"spi"` en
`"ho[spi]tal"`, `"ise"` en `"no[ise]"`, etc.).

### Un exposoma = una distribución a su máxima resolución

Se exporta **una** distribución por exposoma, a la mejor resolución comparable:
la **grilla fina** (por píxel) si al menos dos ciudades tienen un detalle
publicado y verificado (pm25, no2, alan, viento, verde), y si no, su **columna
principal** a nivel administrativo. El descriptor `detail` del manifest v3
—no la mera presencia de un ráster ni el flag global `has_fine_layer`— es lo
autoritativo. Las ~160 columnas derivadas/de
detalle que el picker esconde (`pm25_who_ratio`, `ndvi_mean` vs `evi_mean`,
`precip_rx1day_mm`, `spi_3_mean`, `tmax_p95_c`…) **no se exportan**: son formas
alternativas de calcular el mismo exposoma, no exposomas distintos, y agregaban
ruido al selector. El `master.csv` sigue siendo la fuente de verdad completa
para quien las necesite.

La unidad viene del propio catálogo (`unit`/`unit_long`), ya no de inferencia
por sufijos. El eje X del histograma y de la eCDF imprime esa unidad en el SVG
(esquina inferior derecha); la eCDF suma ticks del eje Y (0 / 0,5 / 1) y su
etiqueta F(x).

### Consecuencia: un riel disperso hoy, que crece con las ciudades

Como la comparación es **entre ciudades**, solo hay distribución para columnas
presentes en ≥2 ciudades. Con Santiago + Buenos Aires eso da hoy **15
exposomas comparables en `entorno`, 3 en `sociedad` y 0 en `resultados`**; el
resto del catálogo (nse, pobreza, crimen, violencia, alimentario, copa, ruido,
metales, mortalidades…) aparece **en gris** ("sin datos comparables"). No es un
bug: refleja el catálogo completo y cada exposoma se ilumina al sumar una ciudad
con ese dato (Lima, Bogotá, CDMX…).

### Histograma en escala log (`log`)

Para indicadores muy sesgados a la derecha (ALAN, precipitación extrema) el
panel ofrece un toggle de **eje X logarítmico**. Los bins log10 se precomputan
en Python (`shared_histogram_log`) y se adjuntan como `entry.log` **solo cuando
el mínimo agrupado es > 0** (log10 indefinido en 0). Deliberadamente **no llevan
bin de desborde**: la compresión
logarítmica ya mantiene la cola en escala. El toggle es una transformación
puramente visual — el webapp remapea la mediana, la banda y la eCDF vía log10 en
el cliente, pero **nunca recalcula un estadístico** (D, A² y p siguen viniendo
del artefacto).

### Lectura textual y medidor de D

El veredicto estadístico se imprime en **prosa** (franja "LECTURA", con cursor
de bloque parpadeante), con los números crudos entre paréntesis como respaldo,
en vez de líneas como `D=0.18 · p=0.0000`. KS se acompaña de un **medidor
horizontal** que ubica D en la escala 0→1 (0 = distribuciones idénticas, 1 = sin
superposición), reforzando la lectura de D como tamaño de efecto por sobre el
p-value. Una pestaña **METODO** dentro del panel condensa esta metodología para
el usuario final.

## Qué queda fuera de v1 (decisiones de alcance, no limitaciones técnicas)

- **Ponderación poblacional y variantes derivadas**: no se exponen en el
  selector. Métricas alternativas del mismo exposoma (p. ej.
  `pm25_pop_weighted`, `pm25_who_ratio`) viven en el `master.csv` pero no en el
  riel, que muestra un exposoma por tarjeta a su máxima resolución. Un toggle de
  "variante ponderada" queda como extensión futura sin romper el JSON.
- **Máscara "solo núcleo urbano"**: el AOI de cada estudio define cuánto
  territorio periurbano/rural entra en la muestra, lo que afecta
  directamente las colas de la distribución. v1 muestra todo dentro del AOI;
  una variante que excluya unidades rurales queda como extensión futura del
  esquema (`mask=urban`), sin romper compatibilidad con el JSON actual.
- **Sin prueba de Wasserstein u otras**: el estadístico D/A² ya cumple el rol
  de tamaño de efecto pedido; se puede añadir después como otra clave dentro
  de `tests` sin cambios estructurales.

## Referencias

- Leys, C., Ley, C., Klein, O., Bernard, P., & Licata, L. (2013). Detecting
  outliers: Do not use standard deviation around the mean, use absolute
  deviation around the median. *Journal of Experimental Social Psychology*,
  49(4), 764-766.
- Rosenmai, P. (2013). Using the median absolute deviation to find outliers
  (double-MAD asimétrico).
- Scholz, F. W., & Stephens, M. A. (1987). K-sample Anderson-Darling tests.
  *Journal of the American Statistical Association*, 82(399), 918-924.
- Armstrong, R. A. (2019). Is there a large sample size problem?
  *Ophthalmic and Physiological Optics*, 39(3), 143-145.
