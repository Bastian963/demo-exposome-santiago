# Ruido ambiental estratégico — España (MER 2022)

Esta capa integra los Mapas Estratégicos de Ruido (MER) de aglomeraciones de
la cuarta fase del Sistema de Información sobre Contaminación Acústica (SICA,
CEDEX/MITECO). La fuente entrega GeoPackage vectoriales de bandas acústicas,
no un ráster: no existe una resolución de píxel que GEMMA pueda atribuirle.

## Cobertura y producto publicado

Se procesan 12 aglomeraciones de Cataluña y 4 del País Vasco. Los contornos
son de todas las fuentes y usan el indicador Lden (día-tarde-noche). GEMMA
intersecta las bandas de >=55 dB(A) con las 43 comarcas catalanas o las 3
provincias vascas y calcula un resumen administrativo. Además publica los
polígonos categóricos sobre su huella modelada como teselas vectoriales MVT
verificadas; no les atribuye una resolución raster en metros.

La métrica principal, `noise_lden_band_mean_dba`, es la media ponderada por
superficie de los puntos medios de las bandas 55--59, 60--64, 65--69, 70--74 y
>75 dB(A): 57, 62, 67, 72 y 77,5 dB(A), respectivamente. Se acompaña de área
afectada >=55 dB(A), área >=65 dB(A), número de aglomeraciones e indicador de
cobertura.

`Barcelonès — piloto MER 2022` es una excepción explícita y pública mientras
se recuperan las fuentes restantes de Cataluña: usa un snapshot independiente
con sólo los GeoPackage validados que intersectan esa comarca. Su nombre,
metadata y nota de cobertura lo identifican como piloto parcial; no habilita ni
representa la release completa de las 43 comarcas catalanas.

## Método

1. Se congela cada ZIP SICA en un snapshot inmutable con checksum SHA-256.
2. Se comprueba CRC del ZIP, integridad SQLite y presencia de
   `NoiseContours_allSourcesInAgglomeration_Lden`.
3. Se reproyectan los polígonos y límites administrativos a EPSG:3035;
   fragmentos de una misma banda se disuelven y todo solape de bandas,
   incluso entre aglomeraciones, se resuelve a favor de la banda más alta.
   Así cada m² aporta una única vez; las fracciones descartadas por solape se
   conservan en la metadata del bundle para auditoría.
4. Se calcula el área de cada banda dentro de cada unidad administrativa y la
   media ponderada correspondiente.
5. Para el detalle web se recorta cada aglomeración al AOI, se simplifica en
   EPSG:3035 con tolerancia máxima de 5 m y se codifica en MVT para zooms
   11--15 con la propiedad categórica `lden_band`. El proceso deja checkpoint
   por aglomeración y se reanuda sólo si coinciden hashes de fuente, AOI y
   parámetros.
6. Antes de copiar las teselas al producto se compara por banda el área cruda,
   resuelta, simplificada y reconstruida desde MVT. El cambio crudo→resuelto
   registra el solape descartado por la prioridad de banda alta; las variaciones
   resuelto→simplificado y simplificado→MVT deben ser <=0,5 %. Las geometrías
   deben seguir siendo válidas, cada tesela comprimida debe ser <=500 kB y la
   peor carga inicial <=2 MB.

Las tablas `ExposureValueInAgglomeration` se entregan como diagnóstico por
aglomeración. No se usan para crear porcentajes por comarca o provincia,
porque el archivo fuente no permite distribuir válidamente esas personas entre
unidades.

## Interpretación

Un valor alto representa una mayor intensidad media entre las áreas ya
cartografiadas por encima de 55 dB(A); no es la media de toda la unidad. Si
`noise_has_modelled_ge55=0`, las métricas son nulas: la unidad no intersecta
contornos utilizables y no debe interpretarse como silenciosa.

## Limitaciones

1. Cobertura limitada a aglomeraciones sometidas al MER; no hay estimación
   regional continua.
2. Las bandas son intervalos y la última es abierta; 77,5 dB(A) es una
   convención reproducible, no una observación del límite superior.
3. El detalle vectorial conserva bandas y contornos, pero la simplificación de
   hasta 5 m y la cuantización MVT no representan fachadas ni mediciones
   puntuales. La vista administrativa sigue siendo un resumen zonal.
4. La capa es una cosecha MER 2022, no una serie anual ni un indicador
   directamente comparable con el porcentaje de población expuesta de Chile.
5. El piloto Barcelonès omite fuentes dañadas y por ello sólo admite
   interpretación sobre el área efectivamente modelada por sus cuatro
   aglomeraciones seleccionadas.
