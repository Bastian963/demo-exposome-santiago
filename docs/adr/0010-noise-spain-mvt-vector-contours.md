# ADR 0010: Los contornos Lden de España se publican como teselas vectoriales MVT verificadas

Fecha: 2026-08-10

## Contexto

El [ADR 0009](0009-barcelona-lden-vector-contours-deferred.md) impidió publicar
como GeoJSON los polígonos MER/SICA 2022: Barcelona sola contiene 4.903.943
vértices y produce cerca de 200 MB sin teselar. La fuente es vectorial en
EPSG:3035 y representa cinco bandas categóricas Lden; no posee tamaño de píxel
ni una resolución raster que GEMMA pueda declarar. MapLibre GL JS 4.7 consume
MVT directamente, por lo que el límite era contractual y de construcción, no
del visor.

## Decisión

1. El contrato v3 admite `detail.type: vector_contours` y
   `rendered.kind: vector_contours` únicamente para un descriptor validado.
   `rendered.resolution` es `null` y la etiqueta pública es «Contornos
   vectoriales MER/SICA».
2. El descriptor usa una plantilla
   `detail/noise_lden/{z}/{x}/{y}.pbf`, zooms 11--15, capa MVT `noise_lden` y
   propiedad categórica `lden_band` con las bandas 55--59, 60--64, 65--69,
   70--74 y >75 dB(A).
3. El constructor parte exclusivamente del `source_manifest.json` congelado,
   verifica los SHA-256 de sus ZIP, extrae los GeoPackage, recorta en EPSG:3035
   al AOI, resuelve solapes a favor de la banda más alta y simplifica con una
   tolerancia máxima de 5 m. Cada aglomeración deja un checkpoint reanudable en
   `cache/`; las teselas sólo se copian a `data/processed` después de pasar las
   pruebas.
4. La prueba registra por banda el área cruda, resuelta, simplificada y
   reconstruida desde MVT. El cambio crudo→resuelto cuantifica transparentemente
   los solapes entre aglomeraciones descartados por la prioridad de banda alta;
   no es pérdida geométrica. La conservación resuelto→simplificado→MVT admite
   una variación <=0,5 %, no pueden aparecer geometrías inválidas y cada banda
   publicada debe decodificarse desde las teselas.
5. Cada tesela debe ocupar <=500 kB comprimida y la peor ventana inicial
   visible debe ocupar <=2 MB. El informe registra inventario, tamaños y hashes;
   `spatial-audit --strict` los vuelve a calcular sobre el bundle publicado.
6. La procedencia se expresa como `source_assets` para cualquier snapshot y,
   cuando hay un único ZIP, también como `source_sha256`. El descriptor declara
   `source_support_preserved: true` y enlaza por hash el informe de validación.
7. La app mantiene el choropleth administrativo atenuado como contexto y
   superpone sólo la huella modelada. El tooltip dice «Banda Lden modelada» y
   nunca «medición» ni un valor interpolado. La leyenda es categórica, de cinco
   bandas, sobre el ancho instrumental fijo de 320 px.

## Puerta y rollout

`barcelona_districts_noise` es el gate: construcción, publicación, auditoría
estricta, pruebas y revisión visual de escritorio/móvil deben pasar antes de
generar `cataluna_comarques` y `pais_vasco_provincias`. El piloto
`barcelones_noise_pilot` sólo se publica si conserva explícitamente su carácter
parcial y supera las mismas puertas; nunca sustituye la release catalana.

## Consecuencias

- El navegador recibe geometría categórica a demanda sin descargar el
  GeoPackage o GeoJSON completo.
- El mapa conserva el soporte vectorial original sin inventar metros por píxel.
- Un descriptor, tesela, hash, banda, zoom o prueba ausente causa fallback
  administrativo en la app y fallo de la auditoría estricta.
- Cambiar ZIP, AOI, bandas, tolerancia, zooms o parámetros MVT cambia la
  identidad del caché y obliga a reconstruir.
