# Extracción puntual de exposomas — metodología

Este documento acompaña a toda descarga generada por la pestaña de descarga de
GEMMA y por `exposome extract-points`. Describe **qué cantidad** contiene cada
fila, cómo se calcula y qué no se puede concluir de ella.

Decisión de respaldo:
[ADR 0012](adr/0012-extraccion-puntual-y-geocodificacion.md).
Contrato de soporte espacial:
[ADR 0004](adr/0004-published-spatial-support-contract.md).

---

## 1. El problema: cambio de soporte

Un indicador de exposoma no tiene un valor «en un punto». Tiene un valor sobre
una **región de soporte**: el píxel satelital, la celda de reanálisis, la unidad
administrativa del registro. Ese soporte puede ser muy grande. En este pipeline
va desde 30 m (dosel arbóreo) hasta 11.132 m (temperatura del aire ERA5-Land),
pasando por 3,5 × 5,5–7 km para la huella observacional de NO₂ (Sentinel-5P).

Pedirle a un dato con soporte de bloque que responda con soporte de punto es el
**problema de cambio de soporte** (*change-of-support problem*), descrito
formalmente en la literatura geoestadística — véase Gotway & Young (2002),
*Combining Incompatible Spatial Data*, y el tratamiento del krigeado de bloques
en Cressie, *Statistics for Spatial Data*. La conclusión relevante es simple: **no
se puede recuperar soporte de punto a partir de soporte de bloque sin un modelo
adicional**, y cualquier método que lo aparente (interpolación bilineal,
remuestreo a una grilla más fina) produce suavizado, no información.

Por eso aquí no se responde «el valor en el punto». Se responde una cantidad
declarada.

## 2. El estimando

Para un punto `x`, un indicador y un radio `r`, la cantidad entregada es:

> **el promedio del indicador sobre la vecindad B(x, r)**, donde `B(x, 0)` es la
> celda o unidad que contiene al punto y `B(x, r)` es el disco de radio `r`.

El radio no es una propiedad del dato: es una **hipótesis de exposición**. Decir
«PM2.5 a 500 m» es afirmar que lo relevante para el desenlace es el aire del
entorno inmediato de la residencia, no el del píxel exacto. Es una decisión de
diseño epidemiológico y por eso se expone al usuario en vez de fijarse.

### 2.1 Estimador para rásters

Con celdas `cᵢ` de valor `vᵢ`:

```
v̂(x, r) = Σ wᵢ·vᵢ / Σ wᵢ        wᵢ = área(cᵢ ∩ B(x, r))
```

Es la media ponderada por área: el estimador no sesgado del promedio de bloque
cuando los datos tienen soporte de bloque. Deliberadamente **no** se usa el
criterio «celdas cuyo centroide cae dentro del buffer», que se sesga cuando `r` es
comparable al tamaño de celda —justamente el régimen en que opera casi todo este
catálogo.

Los pesos se calculan rasterizando **sólo la máscara** del disco a 10× de
submuestreo. Eso computa cobertura fraccional; no remuestrea el dato ni inventa
píxeles.

Con `r = 0` el estimador se reduce a la lectura de la celda contenedora.

### 2.2 Indicadores administrativos: sin mezcla

Los indicadores cuya fuente ya es administrativa (censo, registros de
mortalidad, encuestas socioeconómicas, índices compuestos) devuelven **el valor
de la unidad que contiene el punto**, con `radius_m` vacío. No se promedian entre
unidades vecinas aunque el buffer las toque: el promedio de dos comunas es un
número que no existe en ninguna de las dos, y el propio dato declara que «no se
infiere variación intraunidad».

La fragilidad de borde se informa aparte:

- `units_touched` — cuántas unidades intersecta el disco del radio mayor pedido
- `distance_to_boundary_m` — distancia al límite de la unidad contenedora

Un punto a 80 m de un borde comunal con `units_touched = 3` es un valor que hay
que tratar con cuidado, y eso se dice en vez de disimularlo promediando.

### 2.3 Lo que no se hace

Sin interpolación bilineal, sin krigeado, sin *area-to-point*, sin downscaling
estadístico. La ruta hacia un PM2.5 genuinamente más fino existe y está
documentada en [`plan_b_downscaling.md`](plan_b_downscaling.md) —AOD + covariables
de alta resolución calibradas contra estaciones, con validación
*leave-one-station-out*— pero **no está implementada**, y la extracción puntual no
es un atajo hacia ella.

## 3. Cuándo un radio significa algo

Un buffer más chico que la huella de observación del instrumento no promedia
nada: devuelve el mismo valor que la celda contenedora, con apariencia de haber
promediado.

```
2r ≥ observation_res   →   radius_status = "resolved"
2r <  observation_res   →   radius_status = "sub_observation"
```

La compuerta se calcula contra el soporte de **observación**, no contra la
resolución de descarga ni la de análisis. La diferencia importa: NO₂ se descarga
en una grilla de 1113 m, pero una observación TROPOMI cubre aproximadamente
3,5 × 5,5–7 km. Usando la dimensión mayor (criterio conservador), **todo radio
≤ 3500 m sobre NO₂ es `sub_observation`**.

Los valores `sub_observation` **se entregan igual**, marcados. Sirven para
comparabilidad entre capas; lo que no se puede es leerlos como si describieran
variación a esa escala.

`support_m = max(2r, observation_res)` — el soporte efectivamente entregado, que
nunca es menor que la huella de observación.

### 3.1 Metros de terreno, no metros de proyección

Los COGs publicados están en EPSG:3857 (Mercator web), cuyos metros no son metros
de terreno: a latitud φ, 1 m-Mercator = `cos φ` m de terreno. En
`santiago_communes/annual/detail/pm25_2020.tif`:

| cantidad | valor |
|---|---:|
| `storage_grid.resolution` | 1192,4 m-Mercator |
| equivalente en terreno a −33,45° | 994,9 m |
| `source_native_resolution_m` | 1113,0 m |
| error si se lee el storage como terreno | **−10,6 %** |

Es decir: el número más a mano afirma *más* resolución de la que la fuente
sostiene. Por eso `support_m` y la compuerta de radio se derivan siempre de
`source_native_resolution_m`; la grilla de almacenamiento sólo sirve para indexar
píxeles.

## 4. Radios ofrecidos

| radio | qué significa |
|---|---|
| `0` (celda contenedora) | el valor publicado, sin modelo. **Es el número primario.** |
| 300 m | estándar de acceso a área verde de la OMS (Europa) |
| 500 m | «distancia caminable», ~5–10 min a pie |
| 1000 m | escala de barrio; el mínimo resoluble para PM2.5 (0,01° ≈ 1,1 km) |

La escalera es editable. Se eligió corta a propósito: ampliarla a la escalera
completa que usa la literatura europea de exposoma (100/300/500/1000/1500 m)
multiplica las columnas y la mayoría queda bajo el soporte de casi todas las
capas.

Un **kernel de decaimiento** (gaussiano, por ejemplo) está mejor justificado
físicamente para exposiciones que decaen con la distancia —ruido, tráfico— pero el
buffer de borde duro es el estándar de la literatura y permite comparar con
estudios publicados. Queda como extensión posible, no implementada.

## 5. Incertidumbre reportada

Cada fila trae:

| columna | qué es |
|---|---|
| `value` | el estimador de §2.1 |
| `sd_within_buffer` | desviación estándar ponderada de las celdas contribuyentes. **Sólo cuando `radius_status = resolved`** |
| `n_cells` | celdas fuente que contribuyeron (1 si `r=0`; 0 → sin dato) |
| `coverage_fraction` | fracción de `B(x, r)` con dato válido; `<0,8` se marca `partial_coverage` |
| `support_m` | soporte efectivamente entregado |
| `observation_support_m`, `analysis_support_m` | soportes declarados de la fuente |
| `radius_m`, `radius_status` | `resolved` / `sub_observation` / `not_applicable` |
| `geocode_precision`, `geocode_accuracy_m` | procedencia posicional |
| `quality_flag` | el peor de los anteriores, para filtrar de una |

### 5.1 Por qué `sd_within_buffer` se suprime a veces

Es la mejor medida honesta de **cuánto depende el valor de la ubicación exacta**,
o sea de cuánto importa un geocodificador impreciso en ese sitio concreto.

Pero tiene una inversión traicionera: bajo `sub_observation` todas las celdas
contribuyentes caen dentro de una sola huella de observación, así que la SD tiende
a 0 — y se leería como *alta confianza* precisamente donde el dato es menos
informativo. NO₂ está en ese régimen en todos los radios ofrecidos.

Por eso se emite vacía salvo cuando el radio resuelve. La heterogeneidad local se
comunica entonces por `radius_status` y `support_m`.

## 6. Error de geocodificación

Cuando la entrada es una dirección, el error posicional del geocodificador es
típicamente el término de error dominante. Los órdenes de magnitud habituales en
la literatura de geocodificación (véase Zandbergen 2009 para una revisión) son:

| tipo de match | error típico |
|---|---|
| techo / parcela | 25–100 m |
| interpolación sobre el eje de calle | 100 m – 1 km |
| centroide de localidad | arbitrariamente grande |

Contrastado con los soportes de este catálogo —el ráster más fino es ALAN a
463,83 m, con `canopy` a 30 m como excepción— un error de 50–100 m es
**inmaterial** para PM2.5, NO₂, calor, lluvia y viento: el punto no cambia de
celda. Sí es material para `canopy` y para la proximidad a bordes
administrativos.

Por eso se reporta `geocode_accuracy_m` junto a `support_m` y se deriva:

```
geocode_material = geocode_accuracy_m > 0,5 · support_m
```

El error posicional en estudios de exposición no sesga sólo al azar: en general
**atenúa** las asociaciones exposición-desenlace, y el sesgo depende de si el
error es de tipo Berkson o clásico. Una fila con `geocode_material = true` y
`sd_within_buffer` alta es la que más conviene revisar a mano en el mapa.

Las coordenadas introducidas directamente llevan `geocode_precision =
latlon_exact` y no tienen este término.

## 7. Códigos postales

Un código postal es **un área, no una coordenada**. Cuando la entrada es un
código postal, el resultado se etiqueta como agregado areal sobre la unidad
administrativa publicada, no como una lectura puntual, y no se resuelve a un
centroide: el centroide de un área postal grande no representa a ninguno de sus
habitantes y arrastra el problema de la unidad areal modificable (*MAUP*,
Openshaw 1984) sin declararlo.

**Estado actual:** no existe una referencia postal validada para ninguno de los
países del pipeline, así que esta entrada devuelve `unsupported_country`. Los
códigos postales sólo son geografía real en México, Brasil y España (y
parcialmente Argentina); en Chile, Perú y Colombia la unidad administrativa —
comuna, distrito, localidad— *es* la geografía disponible.

## 8. Alcance y límites conocidos

- **«POIs dentro de 500 m» no está disponible para estudios agregados.** Las capas
  vectoriales (acceso a áreas verdes, entorno alimentario, caminabilidad,
  infraestructura social) publican sólo su resumen administrativo, así que el
  conteo por buffer requiere los `.gpkg` nativos, accesibles por CLI.
- **Un punto fuera de todo estudio publicado** sale marcado `out_of_coverage`, no
  se descarta en silencio ni aborta el lote.
- **La fuente canónica es el COG publicado**, para la webapp y para el CLI por
  igual. La lectura a resolución nativa (`--source native`) existe para estudios
  aún no publicados y produce valores que pueden diferir cerca de bordes de celda,
  porque el teselado es distinto.

## Referencias de orientación

- Gotway, C. A. & Young, L. J. (2002). *Combining Incompatible Spatial Data*.
  Journal of the American Statistical Association — planteamiento formal del
  problema de cambio de soporte.
- Cressie, N. *Statistics for Spatial Data* — krigeado de bloques y soporte.
- Openshaw, S. (1984). *The Modifiable Areal Unit Problem* — por qué el resultado
  depende de la unidad de agregación elegida.
- Zandbergen, P. A. (2009). *Geocoding quality and implications for spatial
  analysis*. Geography Compass — magnitudes del error posicional por tipo de match
  y su efecto sobre el análisis.
- Organización Mundial de la Salud, Oficina Regional para Europa (2016). *Urban
  green spaces and health* — origen del criterio de 300 m.
- Proyecto HELIX (Vrijheid et al.) — convención de buffers residenciales
  múltiples en estudios de exposoma.
