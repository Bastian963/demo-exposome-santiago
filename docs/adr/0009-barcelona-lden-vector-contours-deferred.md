# ADR 0009: Los contornos Lden finos de Barcelona se difieren hasta disponer de teselas vectoriales verificadas

Fecha: 2026-08-06

Estado: sustituido por [ADR 0010](0010-noise-spain-mvt-vector-contours.md) tras
implementar y verificar el contrato y constructor MVT. Este documento conserva
la decisión de aplazamiento y sus presupuestos como registro histórico.

## Contexto

La primera publicación de ruido de Barcelona resume bandas Lden MER/SICA 2022
por los diez distritos municipales. La fuente no es un ráster: contiene
contornos vectoriales modelados por banda. Antes de afirmar un mapa fino se
perfiló localmente el asset `cataluna/barcelona.zip` (SHA-256
`aa09ca582f6345a49ed4f480e090fc42b0f6de8cf7428abb27d7182f30624f88`) contra
el límite oficial de Barcelona.

El [perfil reproducible](../planning/artifacts/barcelona_lden_vector_contours_profile.json)
encontró cinco features >=55 dB(A), pero con 4.903.943 vértices. El GeoJSON
recortado mide aproximadamente 199,8 MB y el GeoParquet 72,9 MB. El origen
materializado ocupa 2,87 GB y el filtro espacial tarda ~87 s incluso antes de
serializar. Publicar ese GeoJSON como detalle de navegador sería lento, frágil
en móvil y no está cubierto por el contrato actual de `detail`.

## Decisión

1. `barcelona_districts_noise` continúa como producto administrativo por
   distrito. Su `detail` permanece `null`; la interfaz debe decir «Mapa
   distrito», nunca píxel o resolución raster.
2. No se publica el GeoJSON ni el GeoParquet crudo de contornos. El mapa fino
   no se habilita por la mera existencia de polígonos fuente.
3. Una futura entrega fina sólo podrá usar teselas vectoriales, no un GeoJSON
   único. Antes habrá que extender explícitamente el contrato v3 para
   `rendered: vector_contours`; no se reutiliza el tipo `geojson` reservado a
   grillas analíticas verificadas.
4. La propuesta de teselas debe cumplir estos límites de aceptación:
   - simplificación métrica de hasta 5 m y zooms 11--15;
   - <=500 kB comprimidos por tesela y <=2 MB para la carga inicial visible;
   - comparación por banda, antes/después de la resolución de solapes, con
     variación de área <=0,5 % y sin invalidar topología;
   - procedencia del ZIP por SHA-256 y `source_support_preserved: true`;
   - tooltip que diga «banda Lden modelada» (por ejemplo 55--59 dB(A)), no una
     medición puntual ni una interpolación.

## Consecuencias

- GEMMA ya ofrece granularidad útil y científicamente honesta en diez
  distritos, sin esperar una infraestructura vectorial inexistente.
- El informe de perfil y su script pueden repetirse cuando cambie el ZIP,
  límite municipal o tolerancia de simplificación.
- Una futura implementación debe añadir constructor de teselas, pruebas de
  conservación por banda, auditoría del manifest y revisión de escritorio y
  móvil antes de publicar el detalle.
